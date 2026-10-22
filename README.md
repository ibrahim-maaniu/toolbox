# toolbox 

Scripts for daily tasks, system setup and networking troubleshooting.

## Windows
[`README.md`](windows/README.md) will have instructions if scripts need any.
| Script | Purpose |
| --- | --- |
| [`setup-sshclient.ps1`](windows/setup-sshclient.ps1) | Quick setup of ssh (ed25519) key and `~/.ssh/config` alias for pubkey-only SSH servers |
| [`initial-winSetup.ps1`](windows/initial-winSetup.ps1) | Initial setup of a fresh windows install. |
| ... | ... |

## Python
[`README.md`](python/README.md) will have instructions if scripts need any.
| Script | Purpose |
| --- | --- |
| [`encode.py`](python/encode.py) | A script to encode video files using FFMpeg as a backend.<br>Created this to help with encoding lots of vid files. |
| ... | ... |

## Conventions 
- Scripts are self-contained unless noted; no shared library required.
- Each script's header docstring lists its own prerequisites and usage.
- Destructive scripts are marked `⚠️` in the table above and require explicit confirmation unless a non-interactive flag is passed.