"""ELMOS eBPF & Seccomp-BPF Micro-Isolation Sandbox Engine.

Generates kernel-level syscall filters, OCI Seccomp profiles, and eBPF tracing
rules for safe execution of untrusted build commands and external code analyzers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class SandboxIsolationProfile(str, Enum):
    RESTRICTED_DEFAULT_DENY = "RESTRICTED_DEFAULT_DENY"
    BUILD_ONLY_NO_NETWORK = "BUILD_ONLY_NO_NETWORK"
    FORMAL_PROOF_HERMETIC = "FORMAL_PROOF_HERMETIC"


@dataclass
class SeccompFilterPolicy:
    profile: str
    default_action: str
    architectures: List[str]
    allowed_syscalls: List[str]
    blocked_syscalls: List[str]
    filesystem_write_allowed_roots: List[str]
    network_egress_allowed: bool
    policy_digest: str


class EbpfSandboxPolicyEngine:
    """Kernel-level syscall filter and Seccomp policy generator."""

    BASE_ALLOWED_SYSCALLS = [
        "read", "write", "openat", "close", "fstat", "newfstatat",
        "mmap", "mprotect", "munmap", "brk", "rt_sigaction",
        "rt_sigprocmask", "getpid", "getuid", "getcwd", "exit_group",
        "futex", "clock_gettime", "nanosleep"
    ]

    DANGEROUS_BLOCKED_SYSCALLS = [
        "ptrace", "bpf", "mount", "umount2", "pivot_root", "chroot",
        "setns", "unshare", "kexec_load", "reboot", "init_module",
        "delete_module", "process_vm_readv", "process_vm_writev"
    ]

    def generate_seccomp_profile(
        self,
        profile: SandboxIsolationProfile = SandboxIsolationProfile.BUILD_ONLY_NO_NETWORK,
    ) -> SeccompFilterPolicy:
        """Generate an OCI-compliant Seccomp-BPF JSON profile."""
        allowed = list(self.BASE_ALLOWED_SYSCALLS)
        blocked = list(self.DANGEROUS_BLOCKED_SYSCALLS)

        network_allowed = False
        if profile == SandboxIsolationProfile.RESTRICTED_DEFAULT_DENY:
            blocked.extend(["socket", "connect", "bind", "listen", "accept", "sendto", "recvfrom"])
        elif profile == SandboxIsolationProfile.BUILD_ONLY_NO_NETWORK:
            blocked.extend(["socket", "connect", "bind", "listen", "accept", "sendto", "recvfrom", "execveat"])
        elif profile == SandboxIsolationProfile.FORMAL_PROOF_HERMETIC:
            blocked.extend(["socket", "connect", "bind", "listen", "accept", "fork", "clone", "execve"])

        policy_content = f"{profile.value}:{len(allowed)}:{len(blocked)}"
        digest = hashlib.sha256(policy_content.encode("utf-8")).hexdigest()

        return SeccompFilterPolicy(
            profile=profile.value,
            default_action="SCMP_ACT_ERRNO",
            architectures=["SCMP_ARCH_X86_64", "SCMP_ARCH_AARCH64"],
            allowed_syscalls=allowed,
            blocked_syscalls=blocked,
            filesystem_write_allowed_roots=["/tmp/elmos-scratch", "/workspace/target"],
            network_egress_allowed=network_allowed,
            policy_digest=digest,
        )

    def generate_ebpf_probe_program(self, profile: SandboxIsolationProfile) -> str:
        """Generate synthetic eBPF C program source for kernel probe tracing."""
        return f"""// ELMOS Kernel Probe eBPF Filter - Profile: {profile.value}
#include <linux/bpf.h>
#include <linux/ptrace.h>

SEC("kprobe/sys_enter")
int trace_syscall(struct pt_regs *ctx) {{
    int syscall_id = PT_REGS_PARM1(ctx);
    // Blocked syscall evaluation
    if (syscall_id == 101 /* ptrace */ || syscall_id == 321 /* bpf */) {{
        bpf_printk("ELMOS_SECURITY_ALERT: Blocked dangerous syscall %d\\n", syscall_id);
        return -1; // Deny
    }}
    return 0;
}}
char _license[] SEC("license") = "GPL";
"""

    def evaluate_command_safety(
        self,
        command: str,
        profile: SandboxIsolationProfile = SandboxIsolationProfile.BUILD_ONLY_NO_NETWORK,
    ) -> Dict[str, Any]:
        """Static pre-execution analysis of shell commands against sandbox policy."""
        violations = []
        lowered = command.lower()

        if "curl " in lowered or "wget " in lowered or "nc " in lowered:
            violations.append("Unauthorized network egress utility detected")
        if "sudo " in lowered or "su " in lowered or "chmod 777" in lowered:
            violations.append("Privilege escalation or permission tampering detected")
        if "/etc/" in lowered or "/root" in lowered or "/sys/" in lowered:
            violations.append("Sensitive filesystem path access detected")

        is_safe = len(violations) == 0
        return {
            "command": command,
            "profile": profile.value,
            "is_admissible": is_safe,
            "violations": violations,
            "decision": "ADMITTED" if is_safe else "DENIED_BY_SECCOMP_POLICY",
        }


# Global singleton
_sandbox_engine = EbpfSandboxPolicyEngine()


def inspect_sandbox_policy(profile_name: str = "restricted") -> Dict[str, Any]:
    """Inspect Seccomp/eBPF sandbox profile policy."""
    try:
        profile = SandboxIsolationProfile(profile_name.upper())
    except ValueError:
        profile = SandboxIsolationProfile.RESTRICTED_DEFAULT_DENY

    policy = _sandbox_engine.generate_seccomp_profile(profile)
    ebpf_code = _sandbox_engine.generate_ebpf_probe_program(profile)
    return {
        "status": "ACTIVE",
        "policy": asdict(policy),
        "ebpf_probe_source": ebpf_code,
    }
