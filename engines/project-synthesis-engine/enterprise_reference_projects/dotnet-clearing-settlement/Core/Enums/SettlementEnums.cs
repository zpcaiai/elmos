namespace Elmos.ClearingSettlement.Core.Enums;

public enum MemberRole
{
    GeneralClearingMember, // Can clear own trades and trades of non-clearing clients
    DirectClearingMember,  // Can clear only own trades
    NonClearingMember      // Must execute through a sponsoring GeneralClearingMember
}

public enum TradeSide
{
    Buy,
    Sell
}

public enum SettlementStatus
{
    Pending,
    Matched,
    Novated,
    Settled,
    Failed,
    Cancelled
}

public enum BatchState
{
    Open,
    Novating,
    Netting,
    Margining,
    Settling,
    Completed,
    DefaultDeclared
}

public enum WaterfallTranche
{
    DefaulterInitialMargin,
    DefaulterDefaultFundContribution,
    CcpSkinInTheGameFirstLoss,
    SurvivingMembersDefaultFund,
    CcpCapitalReserve,
    SurvivingMembersAssessmentCalls
}
