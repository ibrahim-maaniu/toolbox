# toolbox 

Scripts for daily tasks, system setup and networking troubleshooting.

## Windows
| Script | Purpose |
| --- | --- |
| [`windows/setup-sshclient.ps1`](windows/setup-sshclient.ps1) | Quick setup of ssh (ed25519) key and `~/.ssh/config` alias for pubkey-only SSH servers |
| ... | ... |

## Conventions 
- Scripts are self-contained unless noted; no shared library required.
- Each script's header docstring lists its own prerequisites and usage.
- Destructive scripts are marked `⚠️` in the table above and require explicit confirmation unless a non-interactive flag is passed.