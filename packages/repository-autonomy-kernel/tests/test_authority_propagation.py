"""Does a kernel-minted authority reach the next skill in the same dispatch?"""

from __future__ import annotations

import pytest

from elmos_repository_autonomy.dispatcher import AutonomyRuntime, DispatchContext

SHA_POLICY = "sha256:" + "1" * 64


@pytest.fixture()
def runtime():
    return AutonomyRuntime()


@pytest.fixture()
def context(runtime):
    return DispatchContext(tenant_id="t", store=runtime.store,
                           tool_runtime=runtime.tool_runtime)


def authority_request():
    """An environment granting two tools, and a profile narrowed to one."""

    return {
        "environment": {
            "environmentId": "env-1", "workspaceId": "ws-1",
            "policySnapshotHash": SHA_POLICY, "ttlSeconds": 3600,
            "grantedTools": ["echo", "write-file"], "pathScopes": ["src"],
            "networkScopes": [], "secretBindings": [],
        },
        "workspace": {"id": "ws-1"},
        "permission_profile": {"id": "profile-1", "tools": ["echo"], "pathScopes": ["src"]},
        "fencing_token": 4,
    }


def test_the_kernel_path_publishes_the_authority_it_minted(runtime, context):
    result = runtime.execute("execution-authority-kernel", authority_request(),
                             context=context)

    assert "ENGINE:kernel" in result.reasons
    assert context.authority is not None, (
        "the kernel narrowed the authority and nothing downstream can see it"
    )
    assert set(context.authority.allowed_tools) == {"echo"}


def test_the_narrowed_authority_is_what_the_next_skill_sees(runtime, context):
    """The whole point of the authority kernel is that it can only narrow.

    The environment grants `echo` and `write-file`; the profile narrows to
    `echo`. If the narrowed result does not reach the next skill in the same
    dispatch, the tool loader answers from whatever it can find instead - and
    the narrowing was decorative.
    """

    runtime.execute("execution-authority-kernel", authority_request(), context=context)
    loader = runtime.execute("lazy-tool-loader", {
        "tool_catalog": [
            {"tool_id": "echo", "version": "1", "capabilities": ["run"]},
            {"tool_id": "write-file", "version": "1", "capabilities": ["run"]},
        ],
        "step_requirements": ["run"],
    }, context=context)

    loaded = {item["tool_id"] for item in loader.output["loaded_tool_set"]}
    denied = {item["tool_id"] for item in loader.output["denied_tool_set"]}
    assert loaded == {"echo"}
    assert denied == {"write-file"}


def test_the_tool_runtime_does_not_fall_back_to_the_payloads_own_claim(runtime, context):
    """This is the direction that escalates rather than fails closed.

    ``_handle_typed_tool_runtime`` reads ``c.authority or
    ExecutionAuthority.from_payload(p["execution_authority"])``. With the
    kernel-minted authority missing from the context, the ``or`` reaches the
    second operand - the authority the *caller supplied in the payload*. The
    kernel narrowed `echo, write-file` down to `echo` and the tool runtime then
    consults a claim that grants `write-file` anyway.

    The loader's version of this bug fails closed (it loads nothing). This one
    does not: a caller who mints a narrow authority and then presents a wide one
    in the next payload gets the wide one.
    """

    runtime.execute("execution-authority-kernel", authority_request(), context=context)
    assert context.authority is not None
    assert set(context.authority.allowed_tools) == {"echo"}

    result = runtime.execute("typed-tool-runtime", {
        "tool_descriptor": {
            "tool_id": "write-file", "version": "1",
            "input_schema": {"type": "object"}, "output_schema": {"type": "object"},
            "side_effects": False, "allowed_operations": ["run"],
        },
        "tool_call_request": {"tool_id": "write-file", "arguments": {}},
        # A wider claim than the kernel minted.  It must not be consulted.
        "execution_authority": {
            "environment_id": "env-1", "workspace_id": "ws-1",
            "permission_profile_id": "p-wide", "policy_snapshot_hash": SHA_POLICY,
            "fencing_token": 4, "allowed_tools": ["echo", "write-file"],
            "workspace_root": "/workspace",
        },
    }, context=context)

    record = result.output.get("tool_call_record") or {}
    assert record.get("state") != "SUCCEEDED", (
        "the payload's wider authority was honoured over the kernel's narrowed one"
    )
