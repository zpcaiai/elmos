namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.Enums;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Central Counterparty (CCP) Default Management Auction &amp; Juniorization Engine.
/// Implements CPMI-IOSCO Principle 13 (Participant-default rules) and EMIR Article 48 standards.
/// Orchestrates sealed-bid Dutch auctions, clearing member incentive structures,
/// and juniorization of default fund contributions for non-participating/underbidding members.
/// </summary>
public sealed class DefaultAuctionBiddingEngine
{
    public sealed record DefaulterPortfolioSlice(
        string SliceId,
        string DefaulterMemberId,
        IReadOnlyList<TradeContract> Contracts,
        CashAmount EstimatedMarkToMarketValue,
        CashAmount LiquidationReserveFloorPrice,
        DateTime CutoffTimeUtc);

    public sealed record AuctionBid(
        string BidId,
        string MemberId,
        string SliceId,
        CashAmount BidPrice,
        decimal RequestedPortfolioFraction, // 0.0 to 1.0 (e.g., 1.0 for 100% of slice)
        DateTime SubmissionTimeUtc);

    public sealed record AuctionWinningAllocation(
        string MemberId,
        decimal AllocatedFraction,
        CashAmount ExecutionPricePaid,
        bool MetReservePrice);

    public sealed record AuctionResult(
        string SliceId,
        bool AuctionClearedSuccessfully,
        CashAmount ClearingCutoffPrice,
        CashAmount TotalProceedsRealized,
        CashAmount LiquidationShortfallLoss,
        IReadOnlyList<AuctionWinningAllocation> Allocations,
        IReadOnlyList<string> CompliantBiddingMembers,
        IReadOnlyList<string> JuniorizedPenalizedMembers,
        string AuditExecutionLog);

    /// <summary>
    /// Evaluates bids, computes the clearing price, allocates the defaulting portfolio slice,
    /// and identifies members subject to juniorization (whose Default Fund deposits are subordinated).
    /// </summary>
    public AuctionResult RunAuction(
        DefaulterPortfolioSlice slice,
        IReadOnlyList<string> mandatoryParticipantMemberIds,
        IReadOnlyList<AuctionBid> bids,
        decimal minimumAcceptableBidRatioToReserve = 0.85m)
    {
        ArgumentNullException.ThrowIfNull(slice);
        ArgumentNullException.ThrowIfNull(mandatoryParticipantMemberIds);
        ArgumentNullException.ThrowIfNull(bids);

        var currency = slice.LiquidationReserveFloorPrice.Currency;
        var validBids = bids
            .Where(b => b.SliceId == slice.SliceId && b.SubmissionTimeUtc <= slice.CutoffTimeUtc)
            .OrderByDescending(b => b.BidPrice.ToDecimal())
            .ToList();

        var participatingMembers = new HashSet<string>(validBids.Select(b => b.MemberId));
        var juniorizedMembers = new List<string>();
        var compliantMembers = new List<string>();

        // Check participation for all mandatory clearing members
        foreach (var memberId in mandatoryParticipantMemberIds)
        {
            if (memberId == slice.DefaulterMemberId) continue;

            if (!participatingMembers.Contains(memberId))
            {
                // Did not submit a bid: immediate juniorization
                juniorizedMembers.Add(memberId);
            }
            else
            {
                compliantMembers.Add(memberId);
            }
        }

        if (validBids.Count == 0)
        {
            // Complete auction failure
            return new AuctionResult(
                slice.SliceId,
                AuctionClearedSuccessfully: false,
                ClearingCutoffPrice: CashAmount.Zero(currency),
                TotalProceedsRealized: CashAmount.Zero(currency),
                LiquidationShortfallLoss: slice.LiquidationReserveFloorPrice,
                Allocations: Array.Empty<AuctionWinningAllocation>(),
                CompliantBiddingMembers: compliantMembers,
                JuniorizedPenalizedMembers: juniorizedMembers,
                AuditExecutionLog: "Auction failed: Zero valid bids submitted within window.");
        }

        // Dutch auction allocation: allocate fraction down the order of bids until 1.0 (100%) filled
        decimal remainingFraction = 1.0m;
        var allocations = new List<AuctionWinningAllocation>();
        decimal clearingPriceDec = 0m;
        decimal totalProceedsDec = 0m;

        decimal reserveFloorDec = slice.LiquidationReserveFloorPrice.ToDecimal();
        decimal minAcceptableDec = reserveFloorDec * minimumAcceptableBidRatioToReserve;

        foreach (var bid in validBids)
        {
            if (remainingFraction <= 0m) break;

            decimal bidPriceDec = bid.BidPrice.ToDecimal();

            // Check if bid meets reserve tolerance
            if (bidPriceDec < minAcceptableDec)
            {
                // Bid price too low, cannot accept below liquidation hurdle
                if (!juniorizedMembers.Contains(bid.MemberId))
                {
                    juniorizedMembers.Add(bid.MemberId);
                    compliantMembers.Remove(bid.MemberId);
                }
                continue;
            }

            decimal fractionToAllocate = Math.Min(remainingFraction, bid.RequestedPortfolioFraction);
            decimal paymentForFraction = bidPriceDec * fractionToAllocate;

            allocations.Add(new AuctionWinningAllocation(
                bid.MemberId,
                fractionToAllocate,
                CashAmount.FromDecimal(paymentForFraction, currency),
                bidPriceDec >= reserveFloorDec));

            remainingFraction -= fractionToAllocate;
            clearingPriceDec = bidPriceDec; // Marginal clearing price
            totalProceedsDec += paymentForFraction;
        }

        bool cleared = remainingFraction <= 0.0001m;
        var totalProceeds = CashAmount.FromDecimal(totalProceedsDec, currency);
        var shortfallLoss = CashAmount.FromDecimal(
            Math.Max(0m, reserveFloorDec - totalProceedsDec), currency);

        string log = string.Format(
            "Auction {0}: Cleared={1}, Allocated={2:P1}, Proceeds={3} {4}, Shortfall={5} {4}, JuniorizedCount={6}",
            slice.SliceId, cleared, (1.0m - remainingFraction), totalProceeds.ToDecimal(),
            currency.Code, shortfallLoss.ToDecimal(), juniorizedMembers.Count);

        return new AuctionResult(
            slice.SliceId,
            cleared,
            CashAmount.FromDecimal(clearingPriceDec, currency),
            totalProceeds,
            shortfallLoss,
            allocations,
            compliantMembers,
            juniorizedMembers,
            log);
    }

    /// <summary>
    /// Applies the CPMI-IOSCO Juniorization Rule:
    /// Reorders the CCP Default Fund tranche such that non-bidding or uncompetitive members'
    /// contributions are consumed BEFORE winning bidders' default fund contributions.
    /// </summary>
    public IReadOnlyList<MemberInstitution> ReorderDefaultFundTranche(
        IReadOnlyList<MemberInstitution> activeMembers,
        IReadOnlyList<string> juniorizedMemberIds)
    {
        var juniorizedSet = new HashSet<string>(juniorizedMemberIds);

        // Subordinated/Juniorized members come first (absorbed first in default waterfall),
        // followed by compliant bidding members
        return activeMembers
            .OrderByDescending(m => juniorizedSet.Contains(m.MemberId))
            .ThenBy(m => m.MemberId)
            .ToList();
    }
}
