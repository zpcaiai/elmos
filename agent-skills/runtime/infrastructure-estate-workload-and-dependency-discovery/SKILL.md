---
name: infrastructure-estate-workload-and-dependency-discovery
description: Discover and normalize bare metal, VM, operating system, process, middleware, network, storage, certificate, scheduler, workload, dependency, utilization, and ownership evidence. Use for infrastructure estate inventories and landscape twins.
---

# Infrastructure Estate Discovery

## Discovery workflow

1. Bind discovery to an organization, approved scope, environment, account/datacenter, region, and observation window.
2. Inventory datacenters/accounts, regions/zones, networks, hosts/clusters, VMs/nodes, operating systems, processes/services, logical workloads, and applications as separate layers.
3. Record CPU, NUMA, memory, disk, NIC, GPU, firmware, OS/kernel/patch, agents, hypervisor, VM reservations, power, HA, backup, license, owner, and time evidence.
4. Normalize middleware, web/app servers, brokers, ESBs, schedulers, file transfer, cache, directory, configuration, and registry products without hiding business logic.
5. Trace dependencies from connections, configuration, DNS, load balancers, firewall, telemetry, middleware, databases, mounts, and customer declarations.
6. Capture CPU percentiles, memory, IOPS, network, connections, queues, threads, restarts, uptime, and seasonal peaks with explicit window and coverage.
7. Emit immutable estate, host, VM, process, middleware, network, storage, certificate, dependency, and utilization artifacts.

## Safety

Use read-only SSH, WinRM, hypervisor, cloud, CMDB, SNMP, middleware, network, and storage capabilities. Store environment-variable keys and classifications but never values. Store certificate metadata and key references but never private keys. Do not scan addresses, ports, hosts, or accounts outside approved scope.

Mark unknown workload owner, unsupported OS/middleware, single points of failure, shared-host coupling, static IP, local/shared state, expiring certificates, undocumented jobs, unknown network dependencies, and license bindings. Unknown ownership or incomplete estate coverage blocks target provisioning.

