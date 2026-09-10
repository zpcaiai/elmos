namespace Elmos.ClearingSettlement.Engines;

using System;
using System.Collections.Generic;
using System.Linq;
using Elmos.ClearingSettlement.Core.Entities;
using Elmos.ClearingSettlement.Core.ValueObjects;

/// <summary>
/// Bilateral Credit Support Annex (CSA) & Counterparty Exposure Valuation Engine.
/// Computes Net Current Exposure (NCE), Potential Future Exposure (PFE),
/// Minimum Transfer Amount (MTA) thresholds, and automated collateral call demands.
/// </summary>
public sealed class BilateralCreditEngine
{
    public sealed class CsaAgreement
    {
        public string AgreementId { get; }
        public string PartyAId { get; }
        public string PartyBId { get; }
        public Currency ValuationCurrency { get; }
        public CashAmount ThresholdAmount { get; }
        public CashAmount MinimumTransferAmount { get; }
        public CashAmount IndependentAmount { get; }
        public long RoundingIncrementMinor { get; } // e.g. 1,000,000 minor units ($10,000)

        public CsaAgreement(
            string agreementId,
            string partyAId,
            string partyBId,
            Currency valuationCurrency,
            CashAmount thresholdAmount,
            CashAmount minimumTransferAmount,
            CashAmount independentAmount,
            long roundingIncrementMinor = 1_000_000)
        {
            AgreementId = agreementId;
            PartyAId = partyAId;
            PartyBId = partyBId;
            ValuationCurrency = valuationCurrency;
            ThresholdAmount = thresholdAmount;
            MinimumTransferAmount = minimumTransferAmount;
            IndependentAmount = independentAmount;
            RoundingIncrementMinor = roundingIncrementMinor;
        }
    }

    public sealed class BilateralPosition
    {
        public string PositionId { get; }
        public SecurityId SecurityId { get; }
        public Quantity Quantity { get; }
        public CashAmount MarkToMarketPrice { get; }
        public decimal AddOnFactorPfe { get; } // Regulatory PFE factor (e.g. 0.05 for equities, 0.01 for rates)
        public bool IsPartyALong { get; }

        public BilateralPosition(
            string positionId,
            SecurityId securityId,
            Quantity quantity,
            CashAmount markToMarketPrice,
            decimal addOnFactorPfe,
            bool isPartyALong)
        {
            PositionId = positionId;
            SecurityId = securityId;
            Quantity = quantity;
            MarkToMarketPrice = markToMarketPrice;
            AddOnFactorPfe = addOnFactorPfe;
            IsPartyALong = isPartyALong;
        }

        public CashAmount CalculateGrossValue(Currency curr)
        {
            long minorUnits = (long)((decimal)Quantity.Units * (decimal)MarkToMarketPrice.MinorUnits);
            return new CashAmount(minorUnits, curr);
        }
    }

    public sealed class ExposureValuationResult
    {
        public string AgreementId { get; }
        public CashAmount GrossExposureToPartyA { get; }
        public CashAmount GrossExposureToPartyB { get; }
        public CashAmount NetCurrentExposure { get; } // Positive = Party A has exposure to Party B
        public CashAmount PotentialFutureExposure { get; }
        public CashAmount TotalCreditExposure { get; }
        public CashAmount PostedCollateralValue { get; }
        public CashAmount CreditSupportAmountDemanded { get; }
        public bool IsMarginCallTriggered { get; }
        public string DemandingPartyId { get; }
        public string PledgingPartyId { get; }

        public ExposureValuationResult(
            string agreementId,
            CashAmount grossExposureToPartyA,
            CashAmount grossExposureToPartyB,
            CashAmount netCurrentExposure,
            CashAmount potentialFutureExposure,
            CashAmount totalCreditExposure,
            CashAmount postedCollateralValue,
            CashAmount creditSupportAmountDemanded,
            bool isMarginCallTriggered,
            string demandingPartyId,
            string pledgingPartyId)
        {
            AgreementId = agreementId;
            GrossExposureToPartyA = grossExposureToPartyA;
            GrossExposureToPartyB = grossExposureToPartyB;
            NetCurrentExposure = netCurrentExposure;
            PotentialFutureExposure = potentialFutureExposure;
            TotalCreditExposure = totalCreditExposure;
            PostedCollateralValue = postedCollateralValue;
            CreditSupportAmountDemanded = creditSupportAmountDemanded;
            IsMarginCallTriggered = isMarginCallTriggered;
            DemandingPartyId = demandingPartyId;
            PledgingPartyId = pledgingPartyId;
        }
    }

    /// <summary>
    /// Evaluates mark-to-market positions under a bilateral CSA and generates margin calls.
    /// </summary>
    public ExposureValuationResult EvaluateExposure(
        CsaAgreement csa,
        IReadOnlyList<BilateralPosition> positions,
        CashAmount currentCollateralHeldByA,
        CashAmount currentCollateralHeldByB)
    {
        long netMtmMinor = 0;
        long grossAtoBMinor = 0;
        long grossBtoAMinor = 0;
        decimal totalPfeAddOnMinor = 0;

        foreach (var pos in positions)
        {
            long notional = (long)((decimal)pos.Quantity.Units * (decimal)pos.MarkToMarketPrice.MinorUnits);
            decimal pfeAddOn = notional * pos.AddOnFactorPfe;
            totalPfeAddOnMinor += pfeAddOn;

            if (pos.IsPartyALong)
            {
                // Party A is owed if position increases in value
                netMtmMinor += notional;
                grossAtoBMinor += notional;
            }
            else
            {
                // Party B is owed
                netMtmMinor -= notional;
                grossBtoAMinor += notional;
            }
        }

        var curr = csa.ValuationCurrency;
        var netExposure = new CashAmount(netMtmMinor, curr);
        var pfe = new CashAmount((long)totalPfeAddOnMinor, curr);
        var grossA = new CashAmount(grossAtoBMinor, curr);
        var grossB = new CashAmount(grossBtoAMinor, curr);

        // Determine which party has net positive exposure
        bool partyAExposed = netMtmMinor > 0;
        string demandingParty = partyAExposed ? csa.PartyAId : csa.PartyBId;
        string pledgingParty = partyAExposed ? csa.PartyBId : csa.PartyAId;

        long unroundedDemandMinor = 0;
        bool marginCall = false;

        if (partyAExposed)
        {
            // Party A is exposed to Party B:
            // Exposure = Net MTM + Independent Amount - Threshold
            long exposureAboveThreshold = Math.Max(0, netMtmMinor + csa.IndependentAmount.MinorUnits - csa.ThresholdAmount.MinorUnits);
            long collateralDeficit = exposureAboveThreshold - currentCollateralHeldByA.MinorUnits;

            if (collateralDeficit >= csa.MinimumTransferAmount.MinorUnits)
            {
                // Round up to nearest increment
                long increment = csa.RoundingIncrementMinor;
                unroundedDemandMinor = ((collateralDeficit + increment - 1) / increment) * increment;
                marginCall = true;
            }
        }
        else
        {
            // Party B is exposed to Party A:
            long absMtm = Math.Abs(netMtmMinor);
            long exposureAboveThreshold = Math.Max(0, absMtm + csa.IndependentAmount.MinorUnits - csa.ThresholdAmount.MinorUnits);
            long collateralDeficit = exposureAboveThreshold - currentCollateralHeldByB.MinorUnits;

            if (collateralDeficit >= csa.MinimumTransferAmount.MinorUnits)
            {
                long increment = csa.RoundingIncrementMinor;
                unroundedDemandMinor = ((collateralDeficit + increment - 1) / increment) * increment;
                marginCall = true;
            }
        }

        var demand = new CashAmount(unroundedDemandMinor, curr);
        var totalCredit = new CashAmount(Math.Abs(netMtmMinor) + (long)totalPfeAddOnMinor, curr);
        var postedCollat = partyAExposed ? currentCollateralHeldByA : currentCollateralHeldByB;

        return new ExposureValuationResult(
            csa.AgreementId,
            grossA,
            grossB,
            netExposure,
            pfe,
            totalCredit,
            postedCollat,
            demand,
            marginCall,
            demandingParty,
            pledgingParty);
    }
}
