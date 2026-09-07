# ELMOS Security and Compliance Engine

This Java 21 worker is the horizontal security control plane for all ELMOS engines. It exposes the shared `/engine/v1` job contract and `/engine/v1/authorize` for evidence-bound, time-limited **internal** authorization decisions.

All security adapters start `NOT_CONFIGURED`, network is denied by default, active tests require explicit target authorization, secret values are forbidden from evidence, and the worker cannot accept risk or grant ISO, SOC, regulatory, or formal ATO status.
