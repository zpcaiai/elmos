package com.elmos.logistics;

/**
 * Standalone Zero-Dependency Test Suite Runner for Supply Chain & Logistics Engine.
 */
public class LogisticsTestRunner {
    public static void main(String[] args) {
        System.out.println("==========================================================");
        System.out.println("  Java Supply Chain Logistics - Autonomous Test Suite");
        System.out.println("==========================================================");

        int totalSuites = 4;
        int passedSuites = 0;
        int failedSuites = 0;

        try {
            InventoryAllocationEngineTest.runTests();
            passedSuites++;
        } catch (Throwable t) {
            failedSuites++;
            System.err.println("  ✗ InventoryAllocationEngineTest failed: " + t.getMessage());
            t.printStackTrace();
        }

        try {
            WaveRouteOptimizationTest.runTests();
            passedSuites++;
        } catch (Throwable t) {
            failedSuites++;
            System.err.println("  ✗ WaveRouteOptimizationTest failed: " + t.getMessage());
            t.printStackTrace();
        }

        try {
            TransferStateMachineTest.runTests();
            passedSuites++;
        } catch (Throwable t) {
            failedSuites++;
            System.err.println("  ✗ TransferStateMachineTest failed: " + t.getMessage());
            t.printStackTrace();
        }

        try {
            CycleCountReconciliationTest.runTests();
            passedSuites++;
        } catch (Throwable t) {
            failedSuites++;
            System.err.println("  ✗ CycleCountReconciliationTest failed: " + t.getMessage());
            t.printStackTrace();
        }

        try {
            totalSuites++;
            ConcurrencySafetyTest.runTests();
            passedSuites++;
        } catch (Throwable t) {
            failedSuites++;
            System.err.println("  ✗ ConcurrencySafetyTest failed: " + t.getMessage());
            t.printStackTrace();
        }

        try {
            totalSuites++;
            EnterpriseLogisticsAdvancedServicesTest.runTests();
            passedSuites++;
        } catch (Throwable t) {
            failedSuites++;
            System.err.println("  ✗ EnterpriseLogisticsAdvancedServicesTest failed: " + t.getMessage());
            t.printStackTrace();
        }

        try {
            totalSuites++;
            FreightAuditAndCustodyLedgerTest.runTests();
            passedSuites++;
        } catch (Throwable t) {
            failedSuites++;
            System.err.println("  ✗ FreightAuditAndCustodyLedgerTest failed: " + t.getMessage());
            t.printStackTrace();
        }

        System.out.println("\n==========================================================");
        System.out.println("  Test Summary: " + passedSuites + " passed, " + failedSuites + " failed, " + totalSuites + " total");
        System.out.println("==========================================================");

        if (failedSuites > 0) {
            System.exit(1);
        }
    }
}
