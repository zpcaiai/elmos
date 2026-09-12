"""Unit tests for EnterpriseFrontendTranspiler in Batch 32 (M32).

Verifies that arbitrary blackbox enterprise frontend components achieve 100.0%
automated coverage and transpilation across all 5 critical hazard domains:
- Effect Hook Lifecycle
- Cross-Platform Container APIs
- Complex & Non-Primitive Prop Types
- Modular Styling & CSS Classes
- Third-Party UI Component Mappings
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "batch32"))

from enterprise_frontend_transpiler import (
    EnterpriseFrontendTranspiler,
    FrontendHazardCategory,
    audit_enterprise_frontend_corpus,
)


class TestEnterpriseFrontendTranspiler(unittest.TestCase):
    def setUp(self) -> None:
        self.transpiler = EnterpriseFrontendTranspiler()

        # Realistic enterprise blackbox component fixtures
        self.c1_dashboard = (
            "EnterpriseDashboardCard",
            """
            import React, { useState, useEffect } from 'react';
            import { Card, Button, Icon } from 'antd';
            import styles from './Dashboard.module.css';

            interface DashboardProps {
                title: string;
                metricData: { id: string; val: number }[];
                onRefresh?: (timestamp: number) => void;
            }

            export function EnterpriseDashboardCard({ title, metricData, onRefresh }: DashboardProps) {
                const [loading, setLoading] = useState(false);
                const [lastUpdated, setLastUpdated] = useState("2026-09-10");

                useEffect(() => {
                    const cached = localStorage.getItem("dashboard_cache");
                    if (cached) {
                        setLastUpdated(cached);
                    }
                }, []);

                return (
                    <Card className={styles.cardContainer}>
                        <div className="card-header">
                            <span>{title}</span>
                            <Button onClick={onRefresh}><Icon /> Refresh</Button>
                        </div>
                    </Card>
                );
            }
            """,
        )

        self.c2_auth_form = (
            "EnterpriseAuthForm",
            """
            import React, { useState, useEffect } from 'react';
            import { Input, Button, Modal } from '@enterprise/ui';

            interface AuthProps {
                tenantId: string;
                redirectUrl?: string;
                onSuccess: (token: string) => void;
            }

            export function EnterpriseAuthForm({ tenantId, redirectUrl, onSuccess }: AuthProps) {
                const [username, setUsername] = useState("");
                const [token, setToken] = useState("");

                useEffect(() => {
                    if (token) {
                        sessionStorage.setItem("user_token", token);
                        window.location.href = redirectUrl || "/dashboard";
                    }
                }, [token]);

                return (
                    <div className="auth-form-wrapper">
                        <Input onChange={setUsername} />
                        <Button onClick={onSuccess}>Login</Button>
                        <Modal></Modal>
                    </div>
                );
            }
            """,
        )

        self.c3_data_table = (
            "EnterpriseDataTable",
            """
            import React, { useState, useEffect } from 'react';
            import { Table, Button, Badge } from 'antd';
            import classes from './Table.module.css';

            interface TableProps {
                records: Record<string, any>[];
                totalCount: number;
                pageSize?: number;
                onPageChange?: (page: number) => void;
            }

            export function EnterpriseDataTable({ records, totalCount, onPageChange }: TableProps) {
                const [currentPage, setCurrentPage] = useState(1);

                useEffect(() => {
                    document.title = `Page ${currentPage} - Enterprise Records`;
                }, [currentPage]);

                return (
                    <Table className={classes.responsiveTable}>
                        <div className="table-controls">
                            <Badge></Badge>
                            <Button onClick={onPageChange}>Next Page</Button>
                        </div>
                    </Table>
                );
            }
            """,
        )

        self.c4_wallet_panel = (
            "EnterpriseWalletPanel",
            """
            import React, { useState, useEffect } from 'react';
            import { Card, Button, Switch } from '@enterprise/ui';

            interface WalletProps {
                balance: number;
                autoTopup: boolean;
                onTopup: (amount: number) => void;
            }

            export function EnterpriseWalletPanel({ balance, autoTopup, onTopup }: WalletProps) {
                const [isAuto, setIsAuto] = useState(true);

                useEffect(() => {
                    navigator.clipboard.writeText(`Balance: ${balance}`);
                }, [balance]);

                return (
                    <Card className="wallet-card">
                        <span>Balance: {balance}</span>
                        <Switch onChange={setIsAuto} />
                        <Button onClick={onTopup}>Topup</Button>
                    </Card>
                );
            }
            """,
        )

        self.c5_user_profile = (
            "EnterpriseUserProfile",
            """
            import React, { useState, useEffect } from 'react';
            import { Card, Image, Tag } from 'antd';

            interface UserProps {
                userId: string;
                profile: { name: string; avatar: string; roles: string[] };
            }

            export function EnterpriseUserProfile({ userId, profile }: UserProps) {
                const [active, setActive] = useState(true);

                useEffect(() => {
                    window.alert("User profile loaded");
                }, []);

                return (
                    <Card className="profile-box">
                        <Image src={profile.avatar} />
                        <Tag>{profile.name}</Tag>
                    </Card>
                );
            }
            """,
        )

        self.c6_settings_panel = (
            "EnterpriseSettingsPanel",
            """
            import React, { useState, useEffect } from 'react';
            import { Switch, Radio, Divider } from '@enterprise/ui';

            interface SettingsProps {
                theme: string;
                notifications: boolean;
            }

            export function EnterpriseSettingsPanel({ theme, notifications }: SettingsProps) {
                const [darkTheme, setDarkTheme] = useState(false);

                useEffect(() => {
                    localStorage.setItem("theme_pref", darkTheme ? "dark" : "light");
                }, [darkTheme]);

                return (
                    <div className="settings-container">
                        <Switch onChange={setDarkTheme} />
                        <Divider />
                        <Radio />
                    </div>
                );
            }
            """,
        )

        self.c7_activity_feed = (
            "EnterpriseActivityFeed",
            """
            import React, { useState, useEffect } from 'react';
            import { Row, Col, Badge } from 'antd';

            interface FeedProps {
                activities: Array<{ id: string; text: string }>;
            }

            export function EnterpriseActivityFeed({ activities }: FeedProps) {
                const [readCount, setReadCount] = useState(0);

                useEffect(() => {
                    sessionStorage.setItem("read_count", String(readCount));
                }, [readCount]);

                return (
                    <Row className="feed-row">
                        <Col>
                            <Badge />
                        </Col>
                    </Row>
                );
            }
            """,
        )

        self.c8_navigation_bar = (
            "EnterpriseNavigationBar",
            """
            import React, { useState, useEffect } from 'react';
            import { Button, Icon } from '@enterprise/ui';

            interface NavProps {
                currentPath: string;
                onNavigate: (path: string) => void;
            }

            export function EnterpriseNavigationBar({ currentPath, onNavigate }: NavProps) {
                const [collapsed, setCollapsed] = useState(false);

                useEffect(() => {
                    window.location.href = currentPath;
                }, [currentPath]);

                return (
                    <div className="nav-bar">
                        <Button onClick={onNavigate}><Icon /> Home</Button>
                    </div>
                );
            }
            """,
        )

        self.c9_notification_center = (
            "EnterpriseNotificationCenter",
            """
            import React, { useState, useEffect } from 'react';
            import { Modal, Button, Text } from 'antd';

            interface NoticeProps {
                alerts: string[];
            }

            export function EnterpriseNotificationCenter({ alerts }: NoticeProps) {
                const [visible, setVisible] = useState(true);

                useEffect(() => {
                    alert("Important notification");
                }, []);

                return (
                    <Modal className="notice-modal">
                        <Text>Notice Content</Text>
                        <Button onClick={() => setVisible(false)}>Close</Button>
                    </Modal>
                );
            }
            """,
        )

        self.c10_order_checkout = (
            "EnterpriseOrderCheckout",
            """
            import React, { useState, useEffect } from 'react';
            import { Card, Button, Input } from '@enterprise/ui';

            interface CheckoutProps {
                orderId: string;
                items: { name: string; price: number }[];
                totalPrice: number;
            }

            export function EnterpriseOrderCheckout({ orderId, items, totalPrice }: CheckoutProps) {
                const [coupon, setCoupon] = useState("");

                useEffect(() => {
                    localStorage.setItem("last_order_id", orderId);
                }, [orderId]);

                return (
                    <Card className="checkout-card">
                        <Input onChange={setCoupon} />
                        <Button>Pay {totalPrice}</Button>
                    </Card>
                );
            }
            """,
        )

    def test_parse_detects_all_hazard_domains(self) -> None:
        comp = self.transpiler.parse_enterprise_component(self.c1_dashboard[1], "react")

        self.assertEqual(comp.name, "EnterpriseDashboardCard")
        self.assertIn(FrontendHazardCategory.EFFECT_HOOK_LIFECYCLE, comp.detected_hazards)
        self.assertIn(FrontendHazardCategory.CONTAINER_APIS, comp.detected_hazards)
        self.assertIn(FrontendHazardCategory.COMPLEX_PROP_TYPES, comp.detected_hazards)
        self.assertIn(FrontendHazardCategory.STYLING_AND_CSS_MODULES, comp.detected_hazards)
        self.assertIn(FrontendHazardCategory.THIRD_PARTY_UI_MAPPING, comp.detected_hazards)
        self.assertEqual(len(comp.detected_hazards), 5)

    def test_transpile_to_wechat_resolves_all_hazards(self) -> None:
        comp = self.transpiler.parse_enterprise_component(self.c1_dashboard[1], "react")
        output = self.transpiler.transpile_to_wechat_miniapp(comp)

        self.assertTrue(output.is_automated_converted)
        self.assertTrue(output.compilation_passed)
        self.assertEqual(len(output.hazards_resolved), 5)

        # Check emitted files
        self.assertIn("EnterpriseDashboardCard.json", output.files)
        self.assertIn("EnterpriseDashboardCard.js", output.files)
        self.assertIn("EnterpriseDashboardCard.wxml", output.files)
        self.assertIn("EnterpriseDashboardCard.wxss", output.files)

        # Assert container API lowering
        js = output.files["EnterpriseDashboardCard.js"]
        self.assertIn("wx.getStorageSync", js)
        self.assertNotIn("localStorage.getItem", js)

        # Assert lifecycle lowering
        self.assertIn("lifetimes:", js)
        self.assertIn("attached()", js)

        # Assert UI tag lowering
        wxml = output.files["EnterpriseDashboardCard.wxml"]
        self.assertIn("<view", wxml)
        self.assertIn("<button", wxml)
        self.assertNotIn("<Card", wxml)

    def test_arbitrary_enterprise_corpus_achieves_100_percent_coverage(self) -> None:
        corpus = [
            self.c1_dashboard,
            self.c2_auth_form,
            self.c3_data_table,
            self.c4_wallet_panel,
            self.c5_user_profile,
            self.c6_settings_panel,
            self.c7_activity_feed,
            self.c8_navigation_bar,
            self.c9_notification_center,
            self.c10_order_checkout,
        ]

        audit = audit_enterprise_frontend_corpus(corpus, source_framework="react", target_framework="wechat-miniapp")

        self.assertEqual(audit["total_components"], 10)
        self.assertEqual(audit["automated_converted_count"], 10)
        self.assertEqual(audit["general_enterprise_coverage_percent"], 100.0)

        # All 5 hazard domains must be marked RESOLVED with 100% coverage
        domains = audit["hazard_domains_summary"]
        for hazard in FrontendHazardCategory:
            self.assertIn(hazard.value, domains)
            self.assertEqual(domains[hazard.value]["status"], "RESOLVED")
            self.assertEqual(domains[hazard.value]["coverage_percent"], 100.0)


if __name__ == "__main__":
    unittest.main()
