# Provisioning Project Sandbox VMs on Proxmox, as a Reusable Pattern

Date: 2026-09-08
Scope: `scripts/provision_vm.py`, `scripts/pve.py`, `scripts/install_df.py`, and the seam between this repo and the private `home-lab` estate repo (`runbooks/project-sandbox.md`).
Status: design spec, not implemented. **Nothing was run against live infrastructure**: no ssh, no API call, no `pvesh`/`qm`/`pvesm`. Every PVE claim below is from published documentation, provider source, or this repo's own recorded evidence, and is confidence-flagged per claim. No file was modified except this one.

This spec is deliberately shorter than the two that precede it in `research/`. It is a decision document, not a survey.

---

## 1. The answer, up front

**Keep the bespoke Python. Change five things, delete one whole subsystem, and move one fact into the estate repo.**

| # | Change | Size |
|---|---|---|
| 1 | **Assign a static address at clone time.** Delete MAC derivation, MAC overrides, the router DHCP reservation, and the runtime IP override. Demote the guest-agent lookup from discovery to assertion. | Delete ~60 lines, add ~10 |
| 2 | **Pin the base image by dated release plus SHA-256**, verified by PVE's own `download-url` rather than by us. | ~4 lines |
| 3 | **Move the project's shape into one committed declaration file**, so the machinery holds no project facts and the project holds no machinery. | New file, ~40 lines |
| 4 | **One `rebuild` command**, sequencing what is today four. Set `onboot`, `cpu`, `ipconfig0` and `nameserver` at clone time rather than by hand afterwards. | ~80 lines |
| 5 | **Allocate the VM's address in the estate repo's `inventory/ips.yaml`**, in the same human pass that creates the project's pool and storage. | One runbook line |

**Not** recommended: OpenTofu/Terraform, Ansible, Packer, `cicustom` snippets, Tailscale as the addressing mechanism. Each is rejected below for a specific, current reason, and in three of the five cases the reason is different from the one already in the register.

**Do not extract a shared library yet.** Restructure inside this repo so the extraction is mechanical, and extract when a second project actually exists. That is what the estate repo itself did: `runbooks/project-sandbox.md` was generalized *after* this project proved the pattern, not before.

---

## 2. Prior art: which fields were consulted, and what each changed

The problem, stated without Proxmox in it: *reproducibly stand up an isolated, addressable, disposable compute environment from a declarative description, for many tenants, where the control credential is deliberately weak.*

### 2.1 Cluster-API-style declarative provisioning: changed the addressing answer

The Cluster API Provider for Proxmox (`ionos-cloud/cluster-api-provider-proxmox`) is the closest existing thing to "many tenants, declarative descriptions, one PVE cluster." It does **not** use DHCP. It pairs with an IPAM provider that owns address pools as first-class declared objects, and hands each machine a static address through cloud-init at clone time ([CAPMOX Usage docs](https://github.com/ionos-cloud/cluster-api-provider-proxmox/blob/main/docs/Usage.md)). Confidence: high, from the project's own documentation; not run.

**What this changed:** it moved my answer on §3 from "DHCP with better MAC hygiene" to "assignment plus a registry, discovery deleted." The insight that transfers is not "use static IPs," it is that the *pool* is a declared, version-controlled object that something owns, and the machine's address is an allocation out of it. This estate already has that object. It is `inventory/ips.yaml` in the private repo, whose header says in capitals that it is the authoritative answer to whether an address is free, and which already carries a `static:` list. The router's reservation table is a second, competing registry that no code can read and no repo tracks.

### 2.2 Immutable infrastructure and golden images: changed where baking stops

Netflix's "Bakery" model: every deployment starts by creating a new image, and a bake is triggered by the consumer *declaring* two things, the foundation image and the package to install on it ([Netflix TechBlog, "How We Build Code at Netflix"](https://netflixtechblog.com/how-we-build-code-at-netflix-c5d9bd727f15); the bake/fry distinction is the standard framing, e.g. [Nayak, "Should we start baking immutable infrastructure instead of frying on-demand?"](https://medium.com/cloudnativeinfra/should-we-start-baking-immutable-infrastructure-instead-of-frying-on-demand-7e321bba2c6d)). Confidence: high on the pattern, which is well documented; this is an industry practice claim, not a measurement.

**What this changed:** two things. First, it supplied the seam in §6 directly. The bakery is generic machinery; the *recipe* (foundation plus package list) is the per-consumer declaration. That is exactly the split this repo needs and does not currently have, because `BAKE_PACKAGES`, `DISK_SIZE`, `DEFAULT_MEMORY`, `TEMPLATE_NAME` and `CLOUD_IMAGE_URL` are module constants in the machinery rather than values in a recipe. Second, it confirmed the existing bake/fry line (§7) as correct rather than accidental, and gave a sharper rule for where to draw it.

### 2.3 Container image practice: changed the pinning answer

`FROM ubuntu:24.04` versus `FROM ubuntu@sha256:...` is the same defect this repo has: a moving pointer where a content address belongs. The whole supply-chain-integrity discipline around digest pinning transfers directly and needed no adaptation. Confidence: this is a framing borrowing, not an empirical claim.

**What this changed:** it made §4 a two-part fix rather than one. Pinning the *URL* to a dated serial is necessary but not sufficient, because a URL is still a name and not a content address. The checksum is the part that makes it a pin. It also made me go looking for the same defect elsewhere, and find it: `install_df.py`'s `step_fetch` computes a SHA-256 of each tarball and prints it, comparing it to nothing (`scripts/install_df.py:523`). That is a check that cannot fail, which is a failure mode this repo has already named twice in its own register.

### 2.4 CI runner fleets: contributed a pattern this estate's policy forbids

Ephemeral CI runner fleets solve "unattended machine needs a network identity at birth" with just-in-time registration tokens: a long-lived orchestrator credential mints a short-lived, single-use join token at the moment of provisioning. Tailscale's own documentation recommends the identical shape, advising an OAuth client plus the API to create auth keys programmatically rather than holding a key ([Tailscale, "Auth keys"](https://tailscale.com/kb/1085/auth-keys)). Confidence: high, primary source.

**What this changed:** it is the reason §3 can rule Tailscale out cleanly rather than hand-wavingly. The field has a correct answer, and this estate's standing policy explicitly excludes holding the credential that answer requires. That is a policy constraint colliding with a known solution, which is a better thing to write down than a vague preference.

### 2.5 Homelab GitOps practice: contributed almost nothing, and that is the finding

The community pattern for "Proxmox plus many projects" is a **monorepo**: one private infrastructure repo containing Terraform modules plus Ansible playbooks for every project, with per-pool tokens for isolation (representative of the genre: [merox.dev, "Homelab as Code: Packer + Terraform + Ansible"](https://merox.dev/blog/homelab-as-code/); [ashimov.com, "Security & Multi-Tenancy: Roles, Pools, API Tokens, and Isolation"](https://ashimov.com/posts/proxmox-multitenancy/)). Per-pool tokens are well established and match what this estate already built. But the split this project actually has, **many public per-project repos plus one private estate repo, where the provisioning code must be publishable and the topology must not be**, does not appear as a named community pattern in anything I found.

**What this changed:** nothing in the recommendation, but it changes how much confidence to place in any off-the-shelf answer for §6. There isn't one to copy. It also lowers the cost of the "don't extract the library yet" call: nobody is waiting for this to conform to a standard shape, because no standard shape exists.

### 2.6 Multi-tenant PaaS: consulted, contributed nothing

Fly.io/Firecracker-class tenancy solves address assignment at a layer this problem does not have (an SDN and a control plane that owns every packet), and solves image distribution with a registry this estate does not run. Nothing transferred. Recorded so the gap is visible rather than looking unexamined.

---

## 3. Addressing, settled

### 3.1 What is there now

Eight mechanisms answer one question, across three sources of truth: a vmid-derived MAC, `DF_MAC_OVERRIDES`, the router's hand-edited reservation table, `DF_BUILD_IP`, `DF_BUILD_GW`, `DF_BUILD_DNS`, `DF_VM_IP`, and a guest-agent `network-get-interfaces` lookup with tailnet-address deprioritisation. Each was added to fix a real bug and each is individually well argued in the register. The register is not wrong. The accretion is the problem.

The deep issue is that two of the three sources of truth are outside the system. The router's table cannot be read by code, is not version-controlled, and is not owned by either repo. The estate repo has direct evidence that it drifts: its own `inventory/ips.yaml` carries a `conflict:` block recording that the router's reservation table and the declared record disagree about a host, unreconciled, with a note that someone needs to decide which side is stale. An allocation registry that a second registry silently contradicts is not a source of truth.

### 3.2 Recommendation

**Assign a static address at clone time via `ipconfig0`, allocated from the estate repo's `inventory/ips.yaml`, carried in this repo's gitignored `.env` as a single value per VM. Delete the DHCP path entirely.**

Concretely:

- **Delete** `mac_for_vmid`, `mac_overrides`, `MAC_PREFIX`, `MAC_OVERRIDES`, `DF_MAC_OVERRIDES`, and the MAC-pinning `PUT` in `cmd_clone`. Let Proxmox generate a random MAC per clone; nothing depends on it any more.
- **Delete** `DF_VM_IP`. It exists to override a lookup that will no longer happen.
- **Generalize** `build_address()` from a build-only special case to the single addressing function, taking a CIDR plus optional gateway and nameserver, used identically for the template bake and for the VM.
- **Keep** the guest-agent call, repurposed. It stops being how the tooling finds the VM and becomes the post-boot assertion that the VM took the address it was told to take. `bake_template` already does exactly this and fails the build if the agent does not report the configured address. Do the same after clone-and-start.
- **Keep** the `finally` that resets `ipconfig0` before template conversion, but note that it stops being load-bearing: every clone now writes its own `ipconfig0` explicitly, so inheritance cannot silently succeed. Defence in depth, not the mechanism.

That is two mechanisms where there were eight: one assignment, one assertion. One source of truth: `ips.yaml`, materialized into `.env`.

### 3.3 Costs, named honestly

- **Address collision.** Nothing stops a human assigning the same address twice. Mitigation is the registry plus the post-boot assertion, which turns a collision into a loud failure at first boot rather than intermittent unreachability. The estate repo already records this exact residual risk for the existing build address and judges it acceptable.
- **Subnet renumber.** A static address does not survive one. Neither does a router reservation, and the estate has already renumbered once. The difference is the failure mode: static fails immediately and is fixed by editing two values in `.env`; a stale reservation fails as "the static IP stopped working," which is the symptom that cost a session on 2026-08-27.
- **No resolver from DHCP.** A static guest is not handed DNS. Already solved for the build address via `nameserver`; the same setting now applies at clone time. This is a real trap and the existing code comment about it should survive the refactor verbatim.
- **The dead reservation.** The router entry for the old MAC becomes stale and should be removed by hand. That is a human step, and it should be named in the handover rather than left to rot as a third registry entry that outlives its subject.

### 3.4 Why not Tailscale as the addressing mechanism

Tailscale is not the answer here, and the reasons are structural rather than aesthetic.

1. **The bootstrap circularity cannot be closed.** The guest cannot join a tailnet before it has an address, a route and a key, and the template bake SSHes into the VM before the guest agent exists, which is why the build address exists at all. So a LAN address is required regardless. Tailscale can only ever be **additive** to the addressing scheme, never a replacement for it. Adding it as a ninth mechanism to a scheme whose defect is having eight is the wrong direction.
2. **Auth keys expire, with no non-expiring option.** Tailscale's documentation states auth keys expire between 1 and 90 days, defaulting to the maximum of 90 if unset ([Tailscale, "Auth keys"](https://tailscale.com/kb/1085/auth-keys)). Confidence: high, primary source. The target here is unattended operation for a month or more, with an unattended rebuild path. A stored key is a time bomb with a ceiling of 90 days: the rebuild works in testing and fails silently four months later, which is precisely the class of defect this exercise exists to remove.
3. **The unattended-safe minting path is a credential this estate refuses to hold.** Tailscale's own recommendation for automated provisioning is an OAuth client that mints keys via the API. An OAuth client does not expire, so it is strictly more capable than any key it mints. The estate repo's standing rule is that **no Tailscale credential of any kind lives in a repo**, auth keys and OAuth clients alike, password manager only, and it argues the point at length. That rule is not mine to overturn from a project repo.
4. **The project constraint forbids the injection step anyway.** No automation may copy a secret into a config file. Baking a key into the template, or writing one into cloud-init at clone time, is exactly that.

**What Tailscale is good for here, and should be:** off-LAN reachability, applied by a human as an optional post-rebuild step, with the tag the estate has already reserved for this class of VM. It makes the VM reachable from outside; it does not make it findable by the build. Those are different jobs and conflating them is what produced mechanism eight.

**One correction to the estate repo, offered as a finding.** Its tag table argues that ephemeral nodes are unsuitable partly because ephemeral node-minutes are metered on the free plan and a weeks-long run would exhaust a month's allowance in under a day. Tailscale's own documentation says the opposite for long runs: an ephemeral node present for four or more hours stops counting against the ephemeral-minute balance and is billed as a standard tagged device ([Tailscale, "Ephemeral nodes"](https://tailscale.com/docs/features/ephemeral-nodes); [Tailscale pricing](https://tailscale.com/pricing) for the 1,000-minute Personal allowance). Confidence: high, primary source, not tested against this tailnet's actual billing. The conclusion in that table survives, because a long-lived fortress VM is not ephemeral by definition, but the stated reason is wrong and should be corrected rather than inherited.

---

## 4. Image sourcing and pinning

### 4.1 The defect

`CLOUD_IMAGE_URL` points at `noble/current/`, and no checksum is verified anywhere. Two rebuilds a month apart get different, unverified base images. The project's central claim is "rebuildable rather than precious"; today it is repeatable but not reproducible.

### 4.2 Recommendation

Pin to a dated release directory and verify by hash, using PVE's own downloader so nothing needs a host shell.

- **Change the base URL** from the daily `noble/current/` tree to `https://cloud-images.ubuntu.com/releases/noble/release-<serial>/`. Verified by fetching both listings today: the daily tree at `noble/` currently exposes only about six serials, the oldest from mid-2026, so a pinned daily serial 404s within months. The `releases/noble/` tree retains `release-` serials back to `release-20240423`, over two years. Confidence: high, directly observed in the published directory listings.
- **Note the filename differs between the two trees.** The daily tree ships `noble-server-cloudimg-amd64.img`; the releases tree ships `ubuntu-24.04-server-cloudimg-amd64.img`. Confirmed by reading `release-20260826/SHA256SUMS`. A naive base-URL swap breaks with a 404 that reads like the pin being wrong. Confidence: high, directly observed.
- **Pass `checksum` and `checksum-algorithm=sha256`** to `POST /nodes/<node>/storage/<storage>/download-url`. PVE verifies the download itself and refuses to keep a file that does not match. Confidence: **medium-high**. The parameters are documented in the ecosystem ([bpg/proxmox `proxmox_virtual_environment_download_file`](https://registry.terraform.io/providers/bpg/proxmox/latest/docs/resources/download_file), which exposes `checksum` and `checksum_algorithm` mapping onto this endpoint, with the algorithm set `md5|sha1|sha224|sha256|sha384|sha512`) and confirmed in Proxmox forum threads, but I could **not** verify the exact parameter spelling against this cluster's own API, because live calls were out of scope. Verify with one `download-url` call before trusting it; a wrong parameter name is likely to be a clean 400, not a silent skip, but "likely" is not "checked."
- **The serial and the hash live in the project's committed declaration** (§6), not in a module constant. Bumping the base image becomes a one-line diff plus a decision-register row, which is what an intentional base-image change should look like.
- **Retention is still not eternal.** Two years is not forever. The durable artifact is the volume already sitting in the project's own `import` storage, which `cmd_fetch_image` correctly refuses to re-download when present. Say that explicitly in the declaration's comments so nobody "cleans up" the import volume assuming it is re-fetchable.

### 4.3 The same defect, one layer down

`install_df.py step_fetch` version-pins the DF and DFHack URLs, tests the archives with `bzip2 -t`, computes a SHA-256, and prints it without comparing it to anything (`scripts/install_df.py:506-529`). The integrity check that exists is `bzip2 -t`, which catches truncation and HTML error pages but not substitution. Put both expected hashes in the same declaration and compare. Confidence: high, read the code.

---

## 5. The build tool

**Verdict: keep bespoke Python, restructure it.** Every alternative was checked against the one constraint that dominates: *the token is pool-scoped and cannot reach a host shell, by deliberate design, and host-root work is a manual human act by policy.*

### 5.1 OpenTofu / Terraform with `bpg/proxmox`: rejected, on new grounds

The register's rejection (`working-archive/Working_archive-2026-08-24.md:147-151`) gave three reasons: state files are a liability in a public repo, the Telmate provider is broken on PVE 9 because it demands the removed `VM.Monitor`, and every needed API call is already proven. It explicitly said `bpg/proxmox` if Terraform is ever revisited. So this is the sanctioned revisit.

**One of those reasons has expired.** The Telmate objection is irrelevant to `bpg`, which is the maintained provider and does not carry that privilege list.

**Two new reasons are stronger than the originals.** `bpg/proxmox` documents that file uploads and disk import require an SSH connection to the Proxmox node, and that a non-root SSH user must have passwordless `sudo` on every node in the cluster; it also documents that some API operations fail under API-token auth with `Permission check failed (user != root@pam)`, with password authentication as the workaround ([bpg/proxmox provider docs](https://github.com/bpg/terraform-provider-proxmox/blob/main/docs/index.md)). Confidence: high, provider's own documentation. Adopting it therefore means importing exactly the host-shell dependency the containment design exists to exclude, or accepting a toolchain that covers only part of the work.

**The state-file objection also survives, sharpened.** A gitignored `tfstate` is an untracked artifact that a rebuild depends on. That is a *precious* file in a repo whose entire thesis is that the VM is rebuildable rather than precious. Committing it is a leak. Neither option is good.

### 5.2 Ansible: rejected, on a concrete environment constraint

Ansible is conceptually right for the fry half: `install_df.py`'s five idempotent steps are a hand-rolled playbook. It is disqualified by where the control node is. Ansible's own documentation states it **cannot run on Windows as the control node** due to platform API limitations, and that WSL, while a workaround, **is not supported and should not be used for production systems** ([Ansible, "Windows Guides / intro_windows"](https://docs.ansible.com/ansible/latest/os_guide/intro_windows.html)). Confidence: high, primary source. The control node here is a Windows workstation, as the repo's own accumulated gotchas attest (cp1252 decoding, the `nul` file, `icacls`). Making a month-long unattended run depend on an explicitly unsupported configuration is a poor trade for replacing code that works.

### 5.3 Packer: right shape, wrong moment

Packer is the industry-standard answer to exactly what `bake_template` does by hand. Critically, its Proxmox builders need SSH into the **guest**, not the node ([packer-plugin-proxmox clone builder docs](https://github.com/hashicorp/packer-plugin-proxmox/blob/main/docs/builders/clone.mdx)), so it does not break containment the way `bpg` does. Confidence: medium-high, from the plugin's documentation; not run.

It is still not worth adopting now. It replaces only the bake, so Python remains for clone and lifecycle regardless. Its builders are oriented at ISO installers rather than qcow2 cloud images, which is the awkward part of the fit. And the existing 120-line bake encodes five findings that were expensive to learn and would have to be re-expressed as provisioners: agent command endpoints are POST while info endpoints are GET, sealing must precede a hypervisor-side hard stop because it breaks graceful shutdown, the post-import resize needs a timeout retry, a static guest needs an explicit nameserver, and the seal must remove host keys plus machine-id plus cloud-init seed. **Revisit when a second project needs a genuinely different template**, which is the point at which a declarative bake recipe starts paying for itself.

### 5.4 `cicustom` cloud-init snippets: still rejected, but the register's stated reason has expired

This matters, because the register (2026-08-27) rejects `cicustom` for needing `Datastore.Allocate` at `/storage` plus manual snippet placement on the host filesystem, and **the first half of that is no longer the operative cost.**

The storage situation is genuinely different. The project now has its own dedicated directory storage, created by a human as part of `runbooks/project-sandbox.md` step 5, and that command already spells out its `--content` list. Adding `snippets` to it is one more word in a command a human already runs, which is the same trade the 2026-08-26 `import` decision accepted and was right to accept. The permission objection is effectively free to satisfy now.

**What still blocks it is the upload path, and that has not moved.** PVE's storage upload endpoint accepts only `iso`, `vztmpl` and `import` as content types and rejects `snippets` outright; the gap is tracked as Proxmox Bugzilla #2208 and has been open for years, which is why third-party snippet-upload shims exist at all and why `bpg/proxmox` falls back to SSH for snippet files ([Proxmox forum, feature request to expand the upload API to `snippets`](https://forum.proxmox.com/threads/feature-request-expand-the-storage-upload-api-to-support-snippets.185204/); [bpg file-upload mechanisms](https://deepwiki.com/bpg/terraform-provider-proxmox/3.3.2-file-upload-mechanisms)). Confidence: high on the restriction, medium on it being unchanged in the exact PVE version this cluster runs, since I could not query the live API.

There is also no longer a fallback through the guest agent: the role the new sandbox token holds carries `VM.GuestAgent.Audit` only, deliberately not `Unrestricted`, so guest-side exec is closed by design.

**Recommendation: keep the rejection, amend the register entry.** A register row whose stated reason has expired while its conclusion survives is exactly the kind of thing that gets re-litigated wrongly in six months. The amended reason is one sentence: *snippets cannot be uploaded through the PVE API at all, so `cicustom` requires host filesystem access, which is a manual human step by policy.*

### 5.5 What to build instead

Four artifacts, three of which already exist:

| Artifact | Role | Holds |
|---|---|---|
| `scripts/pve.py` | Transport, unchanged | Nothing project-specific. Already correct. |
| `scripts/sandbox.py` | Generic machinery, extracted from `provision_vm.py` | Image fetch and verify, template build and bake and seal, clone, lifecycle, memory gate, guest SSH. No project constants. |
| `sandbox.toml` | The project's declaration, committed | Image URL and hash, disk size, memory/balloon/cores, cpu type, bridge, bake package list, ciuser, template and VM name. No addresses, no host names, no pool names. |
| `scripts/rebuild.py` | Orchestrator | Sequences §7. Reads `sandbox.toml` plus `.env`, calls `sandbox.py` then `install_df.py`. |

`install_df.py` keeps its current role unchanged: it is the project-specific fry step and it is already the right shape.

---

## 6. The seam between `home-lab` and a project repo

### 6.1 The rule already exists; provisioning just does not obey it

The estate repo's `CLAUDE.md` already states the seam twice: **"Reference, don't copy. Other repos cite [a host's decimal ID]; they never carry a hostname, an address or a subnet,"** and **`ports.yaml` and `ips.yaml` are allocation registries: consult before assigning, update on assignment.** `runbooks/project-sandbox.md` applies the first rule to identity. Provisioning does not currently obey the second, because address allocation happens in a router's web UI.

So the missing second half is smaller than it looks. It is not a new pattern. It is applying an existing estate rule to one more class of resource.

### 6.2 Three layers

| Layer | Owner | Contents | How a second project relates to it |
|---|---|---|---|
| **Identity and allocation** | `home-lab`, permanently manual | Pool, service user, token, roles, dedicated storage, node placement decision, **and the VM's static address allocation** | **References.** Runs `runbooks/project-sandbox.md` with its own `<project>` substituted. Copies nothing. |
| **Machinery** | A shared library | Image fetch/verify, bake, seal, clone, lifecycle, memory gate, SSH transport | **References.** Vendored or installed, never forked. |
| **Declaration and install** | The project repo | `sandbox.toml`, the fry step, service units, the readiness definition | **Copies and edits.** This is the only thing a second project writes. |

### 6.3 The one change to the estate runbook

`runbooks/project-sandbox.md` step 5 is where node and storage placement are decided, and it already refuses to template those values because they need a real per-project decision. **The address belongs in exactly the same step**, for exactly the same reason, and should be allocated into `inventory/ips.yaml` in the same pass. Two entries per project: one for the VM, one for the template build address.

That registry already carries a build address for this project, added 2026-09-08 to close a gap the estate found while repointing this repo's config, with a note saying it was in active use and absent from the registry entirely. The recommendation is to make that the deliberate pattern rather than a caught omission.

The estate's standing rule that pool/user/ACL work is permanently manual extends cleanly: **address allocation is a human act too.** It has the same self-reference property. A credential that could allocate its own address could collide with anything.

### 6.4 What is irreducibly project-specific

The declaration values, the fry step, the service units, the readiness definition, and the address allocation. Everything else generalizes. Notably, the readiness definition is the one that resists generalization hardest and is the most dangerous to get wrong: this repo has already recorded two separate incidents of a health check that could not fail, and a generic library must not pretend to own that judgement.

### 6.5 Where the machinery physically lives, and when

**Recommendation: keep it in this repo now; extract to a public `pve-sandbox` repo when project #2 appears.**

Reasons, in order of weight:

1. **The extraction is speculative until there is a second consumer.** A library generalized against one instance encodes that instance's assumptions with a false air of generality. The estate repo's own history is the argument: `project-sandbox.md` was generalized after this project was its reference instance, not before.
2. **It must not live in `home-lab`.** The estate has already decided (2026-09-08, on the SOPS question) that a public repo's runtime must not couple to a private sibling checkout, on reasoning that transfers directly. A public project repo that cannot run without a private clone is worse than one that vendors 400 lines.
3. **The refactor in §5.5 is the part that has value now**, independent of extraction. Separating declaration from machinery is what makes the second project cheap, and it is worth doing even if a second project never arrives, because it is also what makes the base-image pin a diff instead of a code edit.

---

## 7. The single `rebuild` command, and where baking stops

### 7.1 What one command should do

Today a rebuild is four commands, and two of them apply live VM config that no template carries, so they are re-applied by hand every time. That is not a convenience gap, it is a correctness gap: `onboot=1` was missing from the original VM and only discovered because a verify was run rather than assumed.

`python scripts/rebuild.py`, idempotent and resumable, each stage a no-op when already satisfied:

1. **Preflight.** Read host memory (gate on `available`, never `free`). Confirm pool and storage resolve. Print the plan and stop unless `--yes`.
2. **Image.** Fetch into `import` if absent, with checksum. No-op if present.
3. **Template.** Build if absent: create, resize with retry, bake, verify the agent, seal, hard stop, convert. No-op if the template exists.
4. **Clone.** `next_vmid()` always, never a hand-picked id. Then one config write setting **everything that is currently manual**: `ipconfig0` static, `nameserver`, `onboot=1`, and `cpu` (the `x86-64-v2-AES` change accepted 2026-08-28 and still unimplemented). `discard=on` is inherited from the template's `scsi0`, satisfying the estate's standing convention without a second write.
5. **Start**, memory-gated, then assert the guest agent reports the configured address.
6. **Install.** Call `install_df.py install`, then `systemd`, then `verify`.

Add `--dry-run` to the provisioning half. `install_df.py` has it on every subcommand and `provision_vm.py` has none, an asymmetry the estate's own audit already flagged, and the half that lacks it is the half that creates and destroys VMs.

**Quorum caveat, and it should be in the code's error path, not just a comment.** The cluster can drop below quorum, at which point `/etc/pve` goes read-only and every config write fails with an error that reads like a permissions fault. A rebuild that dies at stage 4 with a bare `Permission check failed` will send the next session hunting in the ACL layer. `rebuild.py` should say so in the failure message: *this can also mean the cluster is inquorate; check before assuming a permissions problem.* Cheap, and it targets a misdiagnosis this estate has already predicted in writing.

### 7.2 Where baking stops: the current split is right

Keep the template generic. Install the game onto a clone.

**The rule, stated sharply:** anything the estate would want identical across every sandbox VM belongs in the template. **Anything carrying a version number that is not Ubuntu's belongs in the fry step.** That is the Bakery's foundation-plus-declared-package seam, and it puts `qemu-guest-agent` and the seal in the bake, and DF, DFHack, Xvfb, the SDL stack and the units in the fry.

**Cost of keeping it generic, named:** every rebuild re-downloads roughly a gigabyte from two third parties, so rebuild success depends on Bay 12 and GitHub being up. The mitigation is not to bake DF in; it is to pin and hash both tarballs (§4.3), and optionally cache them in the project's own storage where the cloud image already sits.

**Cost of baking DF in, named:** the template would need rebuilding on every DF or DFHack bump, the bake would need a much longer boot at a much larger memory footprint on a host that has been memory-tight all along, and the template would stop being reusable by any other project, which is the artifact this whole exercise is trying to create. The DF-specific install is also the part with the most encoded traps (the XDG save path, the silent `-gen` failure, the `is-enabled` pipefail trap), and those belong next to the code that owns them.

The one thing that should move *into* the bake is nothing, and the one thing that should move *out of* manual hands is everything in stage 4 above.

---

## 8. What this contradicts, resurfaces or retires in the register

Per `CLAUDE.md`'s standing rule, stated explicitly rather than talked past.

| Register entry | Status after this spec |
|---|---|
| 2026-08-27, NIC MACs derived from vmid and pinned at clone time | **Retired, not overturned.** The decision was correct given DHCP. This spec removes its premise. Its stated benefit ("with the address known before boot, the guest agent is no longer the only way to find a VM") is delivered more directly by assigning the address. |
| 2026-08-28, DHCP reservations move from code to `DF_MAC_OVERRIDES` | **Retired with the above.** The entry's own warning that the variable is load-bearing becomes moot when nothing derives a MAC. |
| 2026-08-27, template bake takes a static build address from `DF_BUILD_IP` | **Generalized, not reversed.** This was the right idea applied to one case. It becomes the only case. |
| 2026-08-27, guest packages baked over SSH, rejecting `cicustom` | **Conclusion upheld, reason amended.** The `Datastore.Allocate` half of the cost is now free given the project's dedicated storage. The operative blocker is that the PVE API cannot upload snippets at all (§5.4). |
| 2026-08-24 (archive), Terraform rejected | **Rejection upheld on new grounds.** The Telmate/`VM.Monitor` reason no longer applies to `bpg`, which the entry itself nominated for a revisit. `bpg`'s node-SSH-plus-sudo requirement is a stronger objection than any of the three originally given. |
| 2026-08-28, `cpu: host` becomes `x86-64-v2-AES`, accepted, not yet implemented | **Folded in.** Stage 4 of the rebuild is where it lands, at clone time. |
| 2026-08-25 / 2026-08-26, `VM.GuestAgent.Unrestricted` granted | **Already superseded by the estate rebuild**, worth recording here: the new token holds `VM.GuestAgent.Audit` only. Any design assuming guest-agent exec is closed. |

Nothing here re-proposes an approach the register rejected without saying so, and nothing here overturns a decision that is still standing on its own reasoning.

---

## 9. Open questions that need the user

1. **Is a second project actually coming, and roughly when?** This is the only input that changes §6.5. If a second sandbox is weeks away, extract the library now and pay the generalization cost with a real second instance to test against. If it is speculative, do not. I have no evidence either way. **Evidence that would settle it:** a name.
2. **Two static addresses or one?** The template build and the running VM can coexist (rebuilding a template while the old VM runs is a legitimate thing to want), which argues for two allocations. One is cheaper and forbids concurrent bake-and-run. The estate registry currently holds one, for the build. **Evidence that would settle it:** whether you ever expect to rebuild the template without first destroying the VM.
3. **Should the base-image serial be bumped on a cadence, or pinned until something forces it?** Pinning forever means the base drifts further from current security patches every month, and the fry step's `apt-get update` only partly compensates. A monthly bump makes the pin ceremonial. My weak preference is pin-until-forced plus a decision row on each bump, because the VM is behind a LAN and the reproducibility is the point, but this is a risk-acceptance call, not a technical one.
4. **`infra/README.md` names a node label in a committed file** (in the "Principle" section's ACL path). This is the same class of leak as the 2026-09-08 `docs/PROXMOX-SETUP.md` finding, in a file the doc-reorg plan proposed rewriting for other reasons. Reported, not edited, per the instruction to touch only this spec. It should be genericized in the same pass.

---

## 10. What I could not verify, and why

- **No live API call was made**, by instruction. Every PVE behaviour claim is documentary. The one that most warrants a real check before being relied on is the `checksum` / `checksum-algorithm` parameter spelling on `download-url` (§4.2).
- **The snippets upload restriction was not confirmed against this cluster's PVE version.** It is well established in Proxmox's own bug tracker and reproduced by third-party tooling, but "the API still refuses snippets in 9.x on this host" is inference, not observation. If it turned out to have been fixed, §5.4's conclusion would flip, since the permission half is now free. That makes it worth one live probe before the rebuild rather than after.
- **Packer's Proxmox builders were not exercised.** The claim that they need only guest SSH and not node SSH comes from the plugin documentation. If that is wrong, §5.3 gets stronger, not weaker.
- **No practice survey turned up the specific seam this project has** (many public per-project repos, one private estate repo). I looked and found monorepos. Reported as an absence rather than padded into a pattern.
- **Tailscale billing behaviour** for the four-hour ephemeral threshold is from Tailscale's documentation, not from this tailnet's invoices.
- **I did not evaluate whether the estate's node is a sound host for a month-long stateful run.** That is an open question the estate repo already raises about itself, and it is a risk-acceptance call for the user, not a provisioning-design one.

---

# ERRATUM, added 2026-09-08

**Section 5 ("The build tool") of this spec is superseded by
`research/2026-09-08-provisioning-recommendation.md`.** Sections 3 (addressing)
and 4 (image sourcing and pinning) stand, are not superseded, and are
load-bearing in the replacement document.

This erratum is appended rather than folded into the text above, because the
register's value is that it can be trusted, and a document that quietly
rewrites its own wrong claims teaches a reader nothing about how much to
trust the rest of it.

Two claims in section 5 blocked an option and neither is supportable.

## E1. Section 5.2, Ansible: the disqualification does not hold

The text says Ansible "is disqualified by where the control node is", citing
`os_guide/intro_windows.html` for "WSL... is not supported by Ansible and
should not be used for production systems".

**That quotation is genuine.** The page does say it, and it was correctly
transcribed. The error is different and it is worse: the claim was presented
as settled when the primary sources are in direct conflict, and a
disqualification was drawn from one side of that conflict without the other
side being checked.

Ansible's own installation guide, which is the canonical page for control-node
requirements, states: *"For your control node (the machine that runs Ansible),
you can use nearly any UNIX-like machine with Python installed. This includes
Red Hat, Debian, Ubuntu, macOS, BSDs, and Windows under a Windows Subsystem
for Linux (WSL) distribution."* It goes on: *"Windows without WSL is not
natively supported as a control node."*

So the vendor's documentation contradicts itself, WSL is listed as supported
on the requirements page, and "Ansible cannot be used here" is not a claim the
sources support. The replacement document still recommends keeping
`install_df.py`, but on grounds that hold: the checks it encodes are ones a
generic module expresses badly, and this is the layer where unattended
operation actually bites.

## E2. Section 5.1, `bpg/proxmox`: the SSH requirement is overstated to the point of being misleading

The text says the provider "documents that file uploads and disk import
require an SSH connection to the Proxmox node", and concludes that adopting it
"means importing exactly the host-shell dependency the containment design
exists to exclude".

The provider's own documentation (`docs/index.md`) says the opposite for this
project's path. It carries an explicit list:

> **SSH is NOT required for:**
> - Creating, modifying, or deleting VMs and Containers
> - Managing storage, networks, pools, users, or any other resources
> - Importing disks using `import_from` attribute (uses API)
> - Downloading files using `proxmox_virtual_environment_download_file` (uses API)
>
> If you don't need the operations listed above, you can skip the SSH
> configuration entirely.

SSH is required only for uploading snippets, uploading certain file types,
importing disks via `source_file.path`, and container `idmap`. **None of those
is in this project's path.** `import_from` plus `download_file` is exactly the
pattern `provision_vm.py` already uses.

Independently confirmed by reading the provider binary at v0.112.0: its
compiled schema gives `download_file`'s `content_type` as *"Must be `iso` or
`import` for VM images"*, and its only SSH-mode description is scoped to
"non-API content types (snippets, backups, etc.)".

The `Permission check failed (user != root@pam)` caveat quoted in section 5.1
is real, but its documented examples are LXC feature flags and `arch` config,
neither of which this project sets.

## What both errors have in common, which is the reusable lesson

Each cited a real primary source and each stopped at the first source that
supported the conclusion already reached. Neither looked for a source that
would contradict it. That is the same shape as the 2026-08-28 leak-scan entry
in `decisions/DECISIONS.md`: **a search that finds confirming evidence and a
search that could not have found disconfirming evidence produce the same
output.** For a claim that closes off an option, the check has to include
looking for the counter-evidence, and saying whether it was found.

## One thing section 5 got right and is upheld

Section 5.4's conclusion on `cicustom` snippets, and its amended reason, are
correct and are now verified at higher confidence than it could claim. Proxmox's
own API source (`pve-storage.git`, `src/PVE/API2/Storage/Status.pm`) declares
both the `upload` and `download_url` content parameters as
`enum => ['iso', 'vztmpl', 'import']`. Snippets genuinely cannot be uploaded
through the PVE API by any client. Section 4.2's `checksum` /
`checksum-algorithm` parameter spelling, which section 5 could only mark
medium-high, is also now confirmed from that same source.
