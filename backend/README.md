# Impact Network Analyzer — SDN Backend

## Current test topology

The current Mininet test topology is:

```text
H1 ── S1 ── R1 ── S2 ── Server
```

IP networks:

```text
H1 side:     10.0.0.0/24
Router:      10.0.0.254/24

Router:      10.0.1.254/24
Server side: 10.0.1.0/24
Server:      10.0.1.10/24
```

### Device roles

- **Mininet** creates the virtual network.
- **Open vSwitch (OVS)** provides the OpenFlow switches S1 and S2.
- **Ryu** controls S1/S2 through OpenFlow 1.3.
- **R1** is a Linux Layer-3 router. It is not an OpenFlow switch; Linux kernel IPv4 forwarding performs routing between the two subnets.
- **Server** is an end device on the 10.0.1.0/24 network.
- **NetworkX** represents the switch graph used for OpenFlow path calculation and a separate heterogeneous device graph used by the project-level analyzer/dashboard.
- **ImpactAnalyzer** measures connectivity loss, rerouting, affected devices and severity.
- **Flask** exposes the topology and impact-analysis APIs.

## Run the SDN test

### First terminal

```bash
source ryu-env/bin/activate
ryu-manager --observe-links ResilientNetworksArp.py
```

### Second terminal

```bash
sudo mn -c
sudo mn --custom topology.py --topo mytopo --controller remote,ip=127.0.0.1,port=6633 --switch ovs,protocols=OpenFlow13
```

Inside Mininet:

```text
nodes
r1 ip addr
server ip addr
h1 ping -c 3 10.0.0.254
r1 ping -c 3 10.0.1.10
h1 ping -c 4 10.0.1.10
```

Expected devices:

```text
c0 h1 r1 s1 s2 server
```

Expected router interfaces:

```text
r1-eth0 = 10.0.0.254/24
r1-eth1 = 10.0.1.254/24
```

## Architecture

```text
                    Ryu Controller
                         |
                    OpenFlow 1.3
                         |
                    +----+----+
                    |         |
                   S1        S2
                    |         |
                   H1         Server
                    \         /
                       R1
                 Linux IP Router
```

The Ryu controller maintains two related views:

1. **OpenFlow routing graph (`self.net`)** — switches and switch-to-switch links only. This is deliberately kept separate so Linux router/server nodes do not break OpenFlow next-hop calculations.
2. **Project device graph (`self.device_graph`)** — hosts, switches, router and server. This graph is exported to `network_state.json` and can be used for device-level impact analysis.

## Failure analysis

For live OpenFlow topology events, the controller detects switch/link changes, analyzes the previous switch graph, refreshes the topology, and clears controller-installed IPv4 forwarding flows so routes can be recalculated.

For project-level simulation, the heterogeneous device graph can also be analyzed for node/link failures involving the router or server.

## Validation performed on the source package

- Python syntax compilation: passed.
- Existing impact-analysis test script: passed.
- Heterogeneous graph analysis for router/link/server failures: passed.

The development environment used for these static checks does not contain Mininet or Ryu, so the final live packet test must be performed in your Ubuntu Mininet/Ryu environment.
