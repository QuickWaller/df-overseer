# Provisioning the Proxmox sandbox VM: the build-tool decision

Date: 2026-09-08
Scope: `scripts/pve.py`, `scripts/provision_vm.py`, `scripts/install_df.py`, and the seam with the private estate repo's `runbooks/project-sandbox.md`.
Status: decision document. **Nothing was run against live infrastructure**: no ssh, no `curl`, no `pvesh`/`qm`/`pvesm`, no API call. Primary sources were opened offline or over the public web, and one provider binary was downloaded from the Terraform registry and read locally.

**Supersedes section 5 ("The build tool") of `research/2026-09-08-vm-provisioning.md`.** That spec's sections 3 (addressing) and 4 (image sourcing and pinning) are upheld and are load-bearing here; two of its build-tool claims were false and are corrected in an ERRATUM appended to that file.

---

## 1. The decision, up front

| Layer | Verdict | Conditional on |
|---|---|---|
| **0. The bake** (not in the original framing) | **DELETE it.** Move `qemu-guest-agent` into `install_df.py`'s `PACKAGES` and assign the address at clone time. | Nothing. Do this first. |
| **1. HTTP transport and retry** (`pve.py`) | **CONFIGURE.** Mount `urllib3.util.Retry` on an `HTTPAdapter`. Do not add POST to `allowed_methods`. | Nothing. Do this regardless of layer 2. |
| **2. VM lifecycle sequencing** (`provision_vm.py`) | **REPLACE** the image, template and clone path with OpenTofu/Terraform plus `bpg/proxmox`. **KEEP** Python for the memory-gated start, `set-memory`, `set-onboot` and everything imperative. | One spike, section 7.4. Stopping rule stated. |
| **3. Guest install** (`install_df.py`) | **KEEP.** No candidate replaces it. | Nothing. |
| **(Identity, placement, address allocation)** | Already off-the-shelf: the estate repo's `runbooks/project-sandbox.md`. Permanently manual by policy. | Nothing. |

Layer 2 is the only place where the user's stated preference changes the answer, and it changes it because the technical objections previously recorded against the off-the-shelf route do not exist. Sections 8 and 9 say exactly how much of the bespoke work this relocates rather than removes, because the honest answer is "more than it removes, and here is the accounting".

---

## 2. Reconciling the preference with the register row committed today

`decisions/DECISIONS.md` 2026-09-08 accepts: *"No shared provisioning library extracted yet; restructure now, extract when a second project is named."* The user has since said they prefer building reusable strong infra over bespoking too often. These look opposed. They are not, and the distinction is the spine of this document.

- **Adopting an existing, externally maintained abstraction is not premature abstraction.** The abstraction exists, someone else maintains it, and the reuse is real on day one. `bpg/proxmox` is that.
- **Extracting your own shared library from bespoke code for a single consumer is premature abstraction.** That is what the register row declines, and declining it is still correct.

Both statements survive intact. The coherent reading is: **be more willing to adopt someone else's reusable thing, and less willing to build your own framework.**

There is a sharper consequence, and it is the strongest single argument in this document. The register row's plan is to *defer* building a shared provisioning library until project two names itself. Adopting `bpg` means **that day never arrives**, because the shared machinery is already someone else's and is already versioned, tested and maintained. Deferring the extraction avoids paying for it today; adopting the provider avoids paying for it ever. The register row is not overturned by this recommendation. It is discharged by it.

A second consequence, which cuts the other way and must be said: **"the existing Python works and is debugged" is a weak argument here**, because it is exactly the argument that makes bespoke the default, and the default is what the user has said they do not want. Incumbency does not carry layer 2 below. Correctness and blast radius still do.

---

## 3. Which fields were consulted, and what each changed

Per the standing rule, the problem stated without Proxmox in it: *choose between a hand-written imperative driver and a general-purpose declarative engine, for a small number of long-lived stateful resources, where the control credential is deliberately weak, the operator is one person, and the target is unattended operation for a month.*

**3.1 SRE retry practice. Changed layer 1 from an unqualified yes to a bounded one.** The discipline's core rule is that retries are safe on idempotent operations and dangerous on everything else, and that a retry policy must not be able to duplicate a side effect. That made me read the installed `urllib3` rather than assume, which produced the fact that actually makes layer 1 safe (section 5): POST is excluded from `DEFAULT_ALLOWED_METHODS`. Without that fact the recommendation would have been "add retry, carefully"; with it, it is "add retry, and the one thing you must not do is widen `allowed_methods`."

**3.2 Distributed-systems failure taxonomy. Contributed the transient/persistent distinction.** A retry policy addresses transient faults. An inquorate cluster is a persistent fault that presents with a permission-shaped error, so no retry configuration can distinguish it from a genuine 403 and no amount of backoff resolves it. The correct treatment is a message in the error path, not a policy. This is why section 5.2 pairs the retry with a text change rather than treating the retry as the whole fix.

**3.3 Immutable infrastructure, cattle versus pets. Changed the drift answer, and supplied the main caution against layer 2.** A declarative engine's normal response to a change it cannot apply in place is to destroy and recreate. That is correct for cattle and hostile to pets. A month-old fortress is a pet: it is the entire experimental output, it cannot be recreated, and this repo's register already flags "destroy this VM" as an adjacent category error for an agent whose remit includes abandoning forts. This did not overturn the layer 2 recommendation, but it produced the guard rails in section 7.2 and section 10.

**3.4 Configuration-management practice, the provisioner/configurer split.** HashiCorp's own position is that provisioners are a last resort. Applying that test to this problem located where bespoke work would be relocated under Terraform: into a `remote-exec` or a null resource wrapping the bake. That is precisely the "relocates the bespoke work somewhere less visible" failure the brief asked me to test for, and it is what made deleting the bake (section 4) a precondition rather than a nice-to-have. With the bake gone, no provisioner is needed and the test passes; with the bake present, it fails.

**3.5 Supply-chain digest pinning. Contributed nothing new.** The prior spec already borrowed this correctly for image pinning and it needed no revision. Recorded so the gap is visible rather than looking unexamined.

**3.6 Homelab GitOps practice. Contributed nothing new, and that remains the finding.** The prior spec looked and found monorepos, not the many-public-project-repos-plus-one-private-estate-repo split this estate actually has. I did not find one either. There is no community shape to conform to here, which is worth knowing: it means no off-the-shelf answer exists for section 9 specifically, only for the executor.

---

## 4. Layer 0: delete the bake. This is the finding that unblocks everything else

The brief asks whether ANY tool removes the boot-install-seal step, or whether it survives every option. **It survives every option as posed, and it does not need to exist at all.**

### 4.1 No tool removes it via cloud-init, and this is now settled at high confidence

Two independent primary sources, both opened for this document:

- **Proxmox's own API source.** `pve-storage.git`, `src/PVE/API2/Storage/Status.pm`: both the `upload` endpoint and the `download_url` endpoint declare their content parameter as `enum => ['iso', 'vztmpl', 'import']`. `snippets` is absent from both. There is therefore no API path by which any client, ours or a provider's, can place a `cicustom` user-data file on the node. Confidence: **high, read from Proxmox's own source.** This confirms the register's 2026-08-27 rejection of `cicustom` and confirms the prior spec's amended reason for it, which it could only mark medium.
- **The `bpg/proxmox` provider binary, v0.112.0, downloaded from the Terraform registry and read locally.** Its compiled-in description of `upload_mode` reads: *"The SSH upload mode for non-API content types (snippets, backups, etc.). `stream` pipes through an SSH shell session and uses sudo where required; `sftp` uploads via the SFTP subsystem and requires direct write permission..."* The maintained provider reaches the same conclusion and falls back to SSH for exactly this class. Confidence: **high, read from the compiled artifact.**

There is a third blocker nobody had recorded. PVE's native cloud-init does expose `ciupgrade`, which would at least run a package upgrade on first boot. `bpg`'s compiled schema documents it as: *"Whether to do an automatic package upgrade after the first boot (defaults to `true` in Proxmox). **Setting this is only allowed for `root@pam` authenticated user.**"* Confidence: **high, read from the provider's own schema.** So even the one native field adjacent to package management is closed to a pool-scoped token. This is the same class of restriction the estate repo already documents for `migration_type` in `runbooks/pve-api-tiers.md`: *"Any API parameter gated on `root@pam` specifically (not on role/ACL) is unreachable by any tier, by design."*

Conclusion: **installing a package into a PVE template through PVE is impossible for this credential, under every tool.** That is a fact about Proxmox and about the containment design, not about Python. It is a major finding for the user's preference: no purchase of an off-the-shelf tool buys past it.

### 4.2 Which is why the package should not go into the template at all

The bake exists for one package, `qemu-guest-agent`, and that package exists for one purpose: letting the API report the VM's address. The prior spec's section 3 already recommends assigning the address at clone time via `ipconfig0` rather than discovering it. **Once the address is assigned rather than discovered, the agent is not needed before the guest install runs, and the package can simply move into the guest install.**

`install_df.py` already apt-installs a package list (`PACKAGES`, `scripts/install_df.py:73`) over SSH on the clone, and already accepts a pinned address in preference to asking the agent (`DF_VM_IP`, `guest_ip()` at `scripts/install_df.py:170`). Both halves of the mechanism are written, debugged and in the repo today.

**The change is: add `"qemu-guest-agent"` to `PACKAGES`, assign `ipconfig0` at clone time, and make `--no-bake` the only mode.**

What that deletes from `provision_vm.py`:

| Deleted | Why it existed |
|---|---|
| `bake_template()`, ~120 lines | To install one package |
| `build_address()`, `DF_BUILD_IP` / `_GW` / `_DNS` | The bake had to SSH in before the agent existed |
| The seal (`cloud-init clean`, host keys, machine-id) | Only needed because the template had been booted |
| The hypervisor-side hard stop | Only needed because the seal breaks graceful shutdown |
| `BAKE_MEMORY`, `BAKE_PACKAGES`, the bake memory gate | Only needed to boot the template |
| The in-bake `/agent/ping` verification | Only needed to prove the bake worked |
| `--no-bake` as a flag | Becomes the only behaviour |

A template that is never booted needs no seal, because there is nothing to seal: Ubuntu cloud images ship with an empty `/etc/machine-id` and no SSH host keys, and cloud-init generates both at each clone's first boot. Confidence: **high on the mechanism, but this specific template has never been built unbaked**, so verify it with the test this repo has already run once (clone twice, compare SSH host key fingerprints and `machine-id`, per the 2026-08-27 seal verification).

Costs, named:

- Every rebuild installs `qemu-guest-agent` on the clone rather than once in the template. Seconds.
- Between clone-start and install-complete the API cannot report the VM's IP. Irrelevant, because the IP is now assigned rather than discovered.
- **The seal lesson stops being enforced by code and becomes a documented condition.** If anyone ever reintroduces a step that boots a VM before converting it to a template, the seal must come back. That belongs in the decision register, not only in a deleted comment.

### 4.3 Why this is the precondition for everything else

With the bake present, adopting any declarative tool means wrapping an imperative boot-ssh-install-seal-stop sequence in a provisioner, which is the "relocated somewhere less visible" outcome the brief warns about. With the bake gone, the entire provisioning job is API calls against declared state, and it is expressible either way. **Do this first. It is worth doing on its own merits even if layer 2 is never touched.**

---

## 5. Layer 1: confirmed, with one correction and one precise constraint

**Verdict: configure `urllib3.util.Retry` on an `HTTPAdapter`. Confirmed as a near-certain win.** `pve.py` mounts no adapter today (`self.session = requests.Session()` with no `session.mount(...)`), so every call is a single unguarded attempt.

**The fact that makes it safe, read from the installed source.** `urllib3` 2.5.0, `urllib3/util/retry.py`, on this workstation:

```
DEFAULT_ALLOWED_METHODS: frozenset({'HEAD', 'TRACE', 'GET', 'PUT', 'OPTIONS', 'DELETE'})
```

**POST is excluded by default.** That is exactly right for this client. `pve.py`'s POSTs create VMs, clone, start, stop and issue agent commands, and a replayed `POST /nodes/<node>/qemu` after a timeout could create two VMs. The GETs, which are what the polling loop is made of, are retried. So the default policy retries precisely the calls that need it and refuses the ones that must never be replayed.

**The one thing not to do: do not add POST to `allowed_methods`.** Doing so converts a correct default into a duplicate-VM hazard. This is the single most important line in the layer 1 change.

Also read from the same file, for whoever tunes it:

```python
backoff_value = self.backoff_factor * (2 ** (consecutive_errors_len - 1))
```

with `DEFAULT_BACKOFF_MAX = 120`, `RETRY_AFTER_STATUS_CODES = {413, 429, 503}`, a `backoff_jitter` parameter defaulting to `0.0`, and a first retry that sleeps zero. `status_forcelist` is empty by default, so a PVE `500` or `502` is **not** retried unless listed. Suggested shape: `total=5, backoff_factor=1.0, backoff_jitter=0.5, status_forcelist=[502, 503, 504]`, leaving `allowed_methods` at its default. Note that the existing `timeout=60` in `PVE.request` becomes per-attempt, not overall.

### 5.1 Two corrections to the brief's framing of this layer

Both matter for sizing the change, and both come from reading the code rather than a summary.

1. **`wait_task`'s default is `timeout=1800`, not 3600**, so most tasks poll about 900 times, not 1800. The 3600 figure is right for exactly two call sites, `cmd_fetch_image` and `cmd_clone`, which do reach roughly 1800 consecutive unguarded GETs. `resize_disk` passes 900, so about 450.
2. **The destroy-on-failure path does not cover the longest operation.** In `cmd_build_template`, the `pve.wait_task(upid, "create VM %s" % vmid)` for the create-plus-25GB-import sits *above* the `try:`. So a dropped GET during the import fails the build and **leaves** the half-built VM; a dropped GET during the resize or the bake fails the build and **destroys** it. Both are real, the blast radii differ, and the fix is the same.

### 5.2 What the retry does not fix, and the change that goes with it

The cluster has no QDevice and can drop below quorum, at which point `/etc/pve` is read-only and writes fail with an error that reads like a permissions fault. That is a persistent fault, not a transient one: no retry policy resolves it, and no `status_forcelist` distinguishes it from a real 403. The correct treatment is a sentence in `PVEError`'s message on 403 and 500 responses: *this can also mean the cluster is inquorate; check quorum before assuming a permissions problem.* Cheap, and it targets a misdiagnosis both repos have already predicted in writing.

**Do layer 1 regardless of layer 2.** `pve.py` survives the layer 2 decision either way, because the operate verbs and `install_df.py` both depend on it.

---

## 6. Layer 3: keep `install_df.py`. Confirmed

**Verdict: keep, unchanged in role.** Ansible is the only serious candidate, it is not disqualified for the reason previously recorded, and it is still the wrong trade.

**Correcting the record on the Windows control node.** Ansible's documentation contradicts itself, and the earlier spec quoted only one side. Both statements are real and both pages were opened for this document:

- `docs.ansible.com/ansible/latest/installation_guide/intro_installation.html`: *"For your control node (the machine that runs Ansible), you can use nearly any UNIX-like machine with Python installed. This includes Red Hat, Debian, Ubuntu, macOS, BSDs, and Windows under a Windows Subsystem for Linux (WSL) distribution."* and *"Windows without WSL is not natively supported as a control node."*
- `docs.ansible.com/ansible/latest/os_guide/intro_windows.html`: *"Ansible cannot run on Windows as the control node due to API limitations on the platform."* and *"The Windows Subsystem for Linux is not supported by Ansible and should not be used for production systems."*

The earlier spec's quotation is genuine. Its error is presenting a contested point as settled and drawing a disqualification from it. The installation guide is the canonical page for control-node requirements and it lists WSL as supported. **The honest finding is a documentation conflict, not a blocker**, and the conflict itself is worth recording, because it is the sort of thing that gets re-litigated wrongly later. Confidence: **high, both pages opened.**

**Why Ansible still loses, on grounds that hold.** `install_df.py`'s value is not that it runs commands over SSH. It is four checks that are correct in a way a generic module is not, each of which cost this repo a session to learn:

- readiness is the socket listening AND an answer that is neither empty nor the connect-error string, with a positive control proving the loop can time out;
- `-gen` success is the region directory existing, never the exit code, because roughly a quarter of runs exit 1 after succeeding, silently;
- the archive SHA-256 must be compared, not merely computed;
- `systemctl is-enabled`, never `list-unit-files | grep -q`, because `grep -q` SIGPIPEs the writer under `pipefail`.

In Ansible these become `ansible.builtin.shell` with `until:` blocks, which is the same shell wrapped in YAML, plus a dependency on the configuration the vendor's own documentation argues about. **This is the layer where "unattended for a month" actually bites**, because this is the layer whose failure modes are silent. Layer 2, by contrast, runs once, at rebuild time, with a human present. That asymmetry is worth stating plainly: the unattended-operation constraint bears hard on layer 3 and barely at all on layer 2.

---

## 7. Layer 2: replace, conditionally. The contest, decided

### 7.1 The two objections previously recorded against `bpg/proxmox` are both false

Verified against the provider's own documentation, opened for this document (`github.com/bpg/terraform-provider-proxmox`, `docs/index.md`). It carries an explicit table of when SSH is required, followed by:

> **SSH is NOT required for:**
> - Creating, modifying, or deleting VMs and Containers
> - Managing storage, networks, pools, users, or any other resources
> - Importing disks using `import_from` attribute (uses API)
> - Downloading files using `proxmox_virtual_environment_download_file` (uses API)
>
> If you don't need the operations listed above, you can skip the SSH configuration entirely.

SSH is required only for: uploading snippets, uploading certain file types, importing disks via `source_file.path`, and container `idmap`. **None of those is in this project's path.** Confidence: **high, provider documentation, corroborated independently by the provider binary**, whose only SSH-mode description is scoped to "non-API content types (snippets, backups, etc.)".

Independently confirmed from the compiled provider schema, downloaded and read locally at v0.112.0:

- `proxmox_virtual_environment_download_file.content_type`: *"The file content type. Must be `iso` or `import` for VM images or `vztmpl` for LXC images."* The `import` content type this project depends on is supported.
- The same resource exposes `checksum` and `checksum_algorithm` (*"Must be `md5` | `sha1` | `sha224` | `sha256` | `sha384` | `sha512`"*), which is the prior spec's section 4.2 recommendation, available for free.
- `proxmox_virtual_environment_vm`'s `disk.import_from`: *"The file id of a disk image to import from storage. Only used during initial creation; changes after creation are ignored."*
- `proxmox_virtual_environment_vm.template`: *"Setting this from false to true converts an existing VM to a template in place."*

The `root@pam` caveat in the provider docs is real. Its documented examples are LXC feature flags and `arch` config, neither of which this project sets. Two attributes must be left unset for that reason and only that reason: `initialization.upgrade` and `cpu.architecture`. Both are named in the spike below.

**So the case against adopting the provider must stand on something else, and the prior spec's version of it does not survive.**

**Free side benefit, independent of the tool decision.** The provider's compiled request struct tags give the exact PVE parameter spelling for `download-url`: `url:"checksum-algorithm,omitempty"`, `url:"content,omitempty"`, `url:"filename,omitempty"`, `url:"verify-certificates,omitempty"`, alongside `checksum`. That closes the prior spec's one medium-high open question (section 4.2, the checksum parameter spelling), and it can be used in `pve.py` today whether or not Terraform is ever adopted. It also matches the Proxmox source read in section 4.1, which independently names `checksum` and `checksum-algorithm` with an enum containing `sha256`. Confidence: **high, two independent primary sources.**

### 7.2 What actually decides it, with incumbency discounted

Applying the preference honestly, the burden of proof sits on keeping the bespoke Python, not on adopting the provider. Working through it:

**In favour of adopting.**

- The executor becomes someone else's maintained artifact: v0.112.0, actively developed, with deep PVE 9 coverage (SDN fabrics, OCI images and the PVE 9 storage resources are all present in the schema).
- It discharges the register's deferred "extract a library later" plan permanently, per section 2.
- Layer 1's problem is solved inside the provider: task polling, per-operation timeouts (`timeout_create`, `timeout_clone`, `timeout_move_disk`) and clone `retries` are all schema attributes.
- The memory gate is expressible declaratively, contrary to my own first assumption. The `proxmox_virtual_environment_node` data source exposes `memory_available` (*"The available memory in bytes on the node"*), so the 2026-08-26 standing rule becomes a `lifecycle { precondition }` rather than a rule a script has to remember.
- Terraform runs natively on Windows. v1.15.8 is already installed on this workstation. No WSL, no contested configuration.
- `terraform plan` gives a drift check against declared intent, which the Python has no equivalent of at all.

**Against, ranked.**

1. **Destroy semantics on a pet (section 3.3).** Several `bpg` attributes force replacement, and a replacement of the fortress VM destroys a month-old fort. Mitigable with `lifecycle { prevent_destroy = true }` on the VM resource and by never running `apply` unattended, but the mitigation is discipline. This is a caution with a named guard rail rather than a disqualifier, because layer 2 is not in the unattended path: it runs at rebuild time with a human reading the plan.
2. **A new file of a class this repo got burned by twice today.** `terraform.tfstate` will contain the pool name, node name, storage id and the static address. It must be gitignored before the first `init`, and the register's own 2026-09-08 lesson applies exactly: *"'Untracked' is not 'safe' in a repo where an agent may run `git add -A`."* Widen `.gitignore` with `*.tfstate`, `*.tfstate.*`, `.terraform/` and `*.tfvars` (keeping a `!*.tfvars.example` negation) as step zero. The state itself is reconstructible for three or four resources via `import` blocks, so the prior spec's "precious file" objection is weaker than it claimed, but the leak class is real and this repo has a fresh scar from it.
3. **A second toolchain, with its own lock file and version discipline.** Small, and partly offset by deleting `provision_vm.py`'s transport concerns.
4. **`import_from` is create-only**, verified above. Bumping the pinned image serial will not rebuild an existing template; the template resource has to be destroyed first. That silently defeats the reproducibility the pin exists for unless the rebuild workflow is explicit about it.

**Decision: adopt, gated on the spike in section 7.4.** The deciding consideration is that with the bake deleted, the provisioning job is entirely declared state reached by API calls, which is the shape a declarative engine is good at, and the alternative is maintaining a hand-rolled equivalent forever in service of a library extraction the register has already agreed not to do.

### 7.3 What stays Python, permanently, and why that is not a defeat

Terraform is a poor fit for imperative preconditions with in-guest side effects, and this project has several. These stay in `pve.py`-driven Python and should not be forced into HCL:

- `start`, gated on live host memory with a `--force` escape. A `precondition` is evaluated at plan time; a start decision wants the reading taken at the moment of starting, on a host whose free memory moved by 4 GiB inside two days.
- `set-memory`, which must refuse against a running VM, because a live write goes through the balloon driver and would report a success that did not happen.
- Everything in `install_df.py`: install, verify, start, stop-with-save, worldgen, backup.

The end state is: **HCL declares what the VM is; Python does what is done to it.** That is a clean seam, not a compromise, and it is the same seam the bake/fry model draws.

### 7.4 The spike, and the stopping rule

The single most important unverified question is whether the pool-scoped token drives `bpg` end to end. Absence of a documented SSH requirement is not proof. Two steps, both runnable in an afternoon, ordered so the cheap one comes first.

**Step A, which is already scheduled and costs nothing extra.** Run the existing Python against the new token:

```
python scripts/provision_vm.py status
python scripts/provision_vm.py fetch-image
python scripts/provision_vm.py build-template --no-bake
```

This proves the two API operations the whole Terraform question turns on, `download-url` into `import` content and VM creation with `import-from`, using code that is already written and already debugged. It is worth running first regardless of the tool decision, because **the estate repo's Phase H is explicitly waiting on one successful `build-template` run before it retires the old identity**, and it is holding an exposed credential open until that happens. A failure here is a token or ACL problem and says nothing about Terraform.

*Stopping rule A.* If `fetch-image` fails with a content-type error, the storage is missing the `import` content type: a one-line human fix in the estate runbook's step 5, not a finding about tools. If it fails with a genuine permission denial on `Datastore.AllocateTemplate` or `Sys.AccessNetwork`, stop; the identity is wrong and neither tool works until it is fixed.

**Step B, the actual spike.** In a scratch directory outside the repo, or inside it only after `.gitignore` is widened per 7.2:

```hcl
terraform {
  required_providers {
    proxmox = { source = "bpg/proxmox", version = "~> 0.112" }
  }
}

# NO ssh {} block. Its absence is the test: if the provider needs a node
# shell for any of the operations below, it fails here with a clear error
# rather than silently working.
provider "proxmox" {
  endpoint  = var.pve_endpoint     # from .env, never committed
  api_token = var.pve_api_token    # pasted by a human, never by automation
  insecure  = true
}

resource "proxmox_virtual_environment_download_file" "cloud_image" {
  node_name          = var.node
  datastore_id       = var.storage
  content_type       = "import"
  url                = var.image_url     # dated release-<serial>, not current/
  file_name          = "noble-server-cloudimg-amd64.qcow2"
  checksum           = var.image_sha256
  checksum_algorithm = "sha256"
}

resource "proxmox_virtual_environment_vm" "template" {
  node_name = var.node
  pool_id   = var.pool
  name      = var.template_name
  template  = true
  started   = false

  agent  { enabled = true }
  cpu    { cores = 4, sockets = 1, type = "x86-64-v2-AES" }   # NOT architecture
  memory { dedicated = 4096, floating = 2048 }

  scsi_hardware = "virtio-scsi-single"
  disk {
    interface    = "scsi0"
    datastore_id = var.storage
    import_from  = proxmox_virtual_environment_download_file.cloud_image.id
    size         = 25
    file_format  = "qcow2"
    discard      = "on"
    ssd          = true
  }

  initialization {
    # deliberately NOT setting `upgrade`: root@pam only
    datastore_id = var.storage
    ip_config { ipv4 { address = "dhcp" } }
    user_account { username = var.ciuser, keys = [file(var.pubkey_path)] }
  }
}
```

Run `terraform plan`, then `apply`, then a second `plan` to confirm it converges to no changes. Then add the clone resource with a static `ip_config`, a `dns` block and `on_boot = true`, and repeat.

*What each outcome means:*

| Result | Verdict |
|---|---|
| Both resources apply, second `plan` is clean | **Adopt.** Proceed to section 11's sequence. |
| Any call fails with `Permission check failed (user != root@pam)` | Identify the attribute. If it is `upgrade` or `architecture`, remove it and retry; those are known. If it is anything else, **stop and keep the Python**: an unknown root-only parameter in the create path is not something a pool-scoped token can be argued around. |
| The provider demands an `ssh` block for any of these | **Stop and keep the Python.** The documentation is then wrong and the containment design is decisive. |
| Apply succeeds but the second `plan` wants to replace the VM | Investigate the attribute. If it cannot be made stable, **stop**: a tool that proposes destroying the fort on every run is worse than no tool. |
| Terraform picks a colliding VMID | See 7.5. Set `vm_id` explicitly from a value a human allocated, or from `provision_vm.py status`'s reported next free VMID, and retry once. If it still collides, **stop.** |

### 7.5 One risk this spike must specifically watch, and which I could not settle

The 2026-08-27 register entry establishes that `next_vmid()` is the only safe source of a VMID, because the pool view is not the host view: a hand-picked id can collide with a VM the token is structurally unable to enumerate. The provider binary contains both a `cluster/nextid` string and a **workstation-local** sequence file (`terraform-provider-proxmox-id-gen.seq`, with a matching `.lock` and the errors "unable to write the ID generator file" and "unable to parse the ID generator file"). If `bpg` allocates from that local file rather than from `/cluster/nextid`, it reintroduces exactly the second-source-of-truth failure that register entry exists to prevent, and a pool-scoped token cannot see the collision coming.

Confidence: **low. This is inferred from strings in a compiled binary, not from reading the Go source, and I did not determine which path is taken when `vm_id` is unset.** The cheap defence is to set `vm_id` explicitly in the declaration, sidestepping the question. The test that settles it: leave `vm_id` unset, apply, and check whether the resulting id matches what `provision_vm.py status` reports as the next free VMID.

---

## 8. What is lost by switching, sorted honestly

`provision_vm.py` encodes about a dozen incidents. The brief's split between "facts about Proxmox" and "artifacts of a hand-rolled client" is right in shape and wrong on two specific rows.

**Facts about Proxmox. These survive every tool and must be re-encoded or deliberately retained.**

| Fact | Where it goes under Terraform |
|---|---|
| `import-from` refuses an `iso`-class volume; needs `images` or `import` | Encoded in the provider: `content_type` must be `iso` or `import`. Free. |
| The downloaded `.img` must be stored as `.qcow2` on an import store | `file_name` on the download resource. Note the provider documents a **version-dependent inverse** of this trap: *"PVE will raise 'wrong file extension' error for some popular extensions file `.raw` or `.qcow2` on PVE versions prior to 8.4. Workaround is to use e.g. `.img` instead."* Our finding and theirs point opposite ways, so this must be tested on this cluster's version and assumed in neither direction. |
| Gate on `available` memory, never `free` | `data.proxmox_virtual_environment_node.memory_available`, plus the Python `start` gate, which stays. |
| A static guest is handed no resolver; needs an explicit nameserver | `initialization.dns`. Must be carried over deliberately; forgetting it is a silent failure at the first name lookup. |
| The post-import resize can time out under storage flush | **Loses its retry.** `bpg` exposes `timeout_create` and `timeout_move_disk` but no equivalent retry-on-timeout. Re-encode as a generous timeout and expect to tune it. This is the clearest single capability regression. |
| A live `memory` write goes through the balloon and does not move the ceiling | Stays in Python (`set-memory`). Untouched. |
| `onboot` applies live and is a scheduling flag, not an allocation | `on_boot`. Free. |
| The seal, if a VM is ever booted before conversion | Retired as code by section 4, retained as a register condition. |
| Snippets cannot be uploaded through the API at all | Retained as a register amendment. Now verified from Proxmox's own source. |
| `ciupgrade` and `arch` are `root@pam` only | New this document. Belongs in the register. |
| `sshkeys` must be URL-encoded before entering the form body | Absorbed by the provider. Genuinely disappears. |
| `next_vmid()` is the only safe source of a VMID | **At risk.** See 7.5. Do not let this lapse silently. |

**Artifacts of the hand-rolled client. These genuinely disappear.**

- The agent verb asymmetry: `GET /agent/ping` returns `501`, commands are POST and info endpoints are GET. Disappears as code. Keep it as prose anyway, because the error message actively misleads and a human will hit it again in `pvesh`.
- The `_require()` refactor that left `self.session.headers["Authorization"]` unreachable. A self-inflicted bug in code that would no longer exist.

**Two rows the brief put in the wrong bucket.**

- **The cp1252 decode failure is not a hand-rolled-HTTP artifact.** It is a Windows `subprocess` artifact in `ssh_guest`, which `install_df.py` imports and which survives under every option including Terraform. So does the sibling `nul`-file trap from `os.devnull` on Windows, and the MSYS path-rewriting hazard that is the documented reason `pve.py` is Python rather than bash. All three are consequences of the control node, not of the HTTP client.
- **The resize timeout retry is not a client artifact either.** It is a fact about storage flushing after a 25 GB import, and it survives as a regression, per the table above.

**Net accounting, so the relocation is visible.** Adopting the provider deletes roughly 200 lines of Python from `provision_vm.py` (on top of the ~150 the bake deletion already removes) and adds roughly 150 lines of HCL, a provider lock file and a state discipline. It leaves `install_df.py` (1151 lines) and the operate verbs entirely untouched, which is the majority of the code and all of the project-specific value.

**So at layer 2 the off-the-shelf route relocates more bespoke work than it removes.** It removes work outright only at layer 1. The layer 2 recommendation therefore rests on maintenance ownership and on discharging the deferred library extraction, not on a line-count win, and it should not be sold as one.

---

## 9. Reusability: what a second project actually reuses

This is the user's real ask, and the answer has to be concrete. Four artifacts, three homes.

| Artifact | Home | How project two consumes it |
|---|---|---|
| **Identity, placement, storage content types, address allocation** | The private estate repo, `runbooks/project-sandbox.md` | **Substitutes `<project>` and runs it.** Copies nothing. Permanently manual by policy, including the address allocation, which should be added to its step 5 alongside node and storage, into the estate's own IP allocation registry. This is already the strongest reuse this estate has, and it is entirely tool-independent. |
| **The executor** | `bpg/proxmox`, someone else's repo | **Declares `required_providers`.** Nothing to maintain, nothing to fork. This is the whole point of the recommendation. |
| **The wiring: ~150 lines of HCL with no project facts in it** | This repo now, as one variables-driven file. A public `pve-sandbox` module repo the day project two is named. | **Copies and edits today; `source = "git::..."` later.** Writing it variables-driven from the start makes that promotion mechanical rather than a rewrite. |
| **The declaration and the fry step** | The project repo | **Copies and edits the declaration; writes its own fry step.** Irreducibly per-project. |

**The wiring must not live in the estate repo.** That repo has already decided (2026-09-08, on the SOPS question) that a public repo's runtime must not couple to a private sibling checkout, and the reasoning transfers directly.

**The counterfactual, said out loud rather than left implicit.** If layer 2 stays Python, what does project two reuse? **The runbook, and nothing else executable.** They copy `provision_vm.py` into their own repo and edit it, or they wait for a shared library this repo has committed not to build for a single consumer. That is a real answer, and it is exactly the asymmetry the user is intuiting: a Terraform module is estate infrastructure with a standard consumption story, and a Python script inside one project repo is not, however well written. It is also the argument that carries layer 2, once incumbency is discounted.

**One caution against over-reading this.** The HCL is ~150 lines. It is not where the value is. The value is in the runbook, which is already reusable, already off-the-shelf and already done, and in the fry step, which is never reusable by nature. Adopting the provider improves the middle third of a three-part picture. It does not transform it, and anyone selling it as transformational is selling something.

---

## 10. State and drift

**Verdict: a manageable problem, with three named guards.**

The mutations `install_df.py` and systemd perform are to the **guest filesystem**, and Terraform's state describes **PVE's view of the VM**. They do not overlap, so the obvious fear is unfounded: installing Dwarf Fortress does not make `terraform plan` dirty. Confidence: high; this follows from what the resource schema actually tracks.

The three real issues:

1. **`import_from` is create-only** (verified in the schema), so a pinned-image bump is a silent no-op on an existing template. Guard: comment it in the declaration, and make "destroy the template resource, then apply" the documented image-bump procedure.
2. **Cloud-init changes need a full stop and start** to take effect, not a reboot. Guard: the rebuild path always starts from a fresh clone, so this only bites someone editing a live VM's `initialization`.
3. **Replacement is the failure mode that matters.** Guard: `lifecycle { prevent_destroy = true }` on the fortress VM resource, and never run `apply` unattended. The template resource does not need the guard; it is genuinely disposable, which is the whole point of it.

A fourth, procedural: **widen `.gitignore` before `terraform init`**, per 7.2.

---

## 11. Migration path, with a stopping rule at every step

Nothing is running: the template and the VM were both deleted 2026-09-01. There is no state to migrate. **This is the cheapest moment this decision will ever have, and that argues for making it now rather than after a fort exists.** It equally argues for keeping each step independently valuable, so that stopping early still leaves the repo better off.

| # | Step | Value if you stop here | Stopping rule |
|---|---|---|---|
| 1 | **Layer 1.** Mount `Retry`. Add the inquorate hint to the error path. Do not touch `allowed_methods`. | Removes the single-blip build failure. Survives every later decision. | None. Unconditional. |
| 2 | **Layer 0.** Delete the bake: `qemu-guest-agent` into `PACKAGES`, static `ipconfig0` at clone time, `--no-bake` becomes the only mode. Adopt the prior spec's section 3 addressing and section 4 image pin in the same pass. | ~150 fewer lines, three fewer `.env` values, one fewer source of truth. Worth doing even if nothing else happens. | If two clones from an unbaked template share a `machine-id` or an SSH host key fingerprint, the seal is still required: restore the bake and stop. |
| 3 | **Spike A.** Run `status`, `fetch-image`, `build-template --no-bake` on the new token. | Discharges the estate repo's Phase H and lets an exposed credential be retired. Independently required. | Per 7.4. A failure here is an identity problem, not a tool problem. |
| 4 | **Spike B.** The `bpg` config in 7.4, with no `ssh` block. | Settles the token question definitively, either way. | Per the table in 7.4. Any `root@pam` denial outside the two known attributes, or any SSH demand, stops the migration; the Python stands with steps 1 and 2 already banked. |
| 5 | **Adopt.** Move image, template and clone to HCL. Delete the corresponding Python. Keep `pve.py`, `start`, `set-memory`, `set-onboot` and all of `install_df.py`. | The recommendation, delivered. | If the second `terraform plan` after a successful apply is not clean and cannot be made clean, revert to the Python: an engine that cannot converge is worse than a script. |
| 6 | **Write the register rows**, per section 13. | The lessons survive the code that taught them. | None. |

Steps 1 and 2 are unconditional and independent of the tool choice. Steps 3 through 5 are the conditional part. **A reader who does only steps 1 and 2 has still banked most of the practical benefit**, which is deliberate.

---

## 12. What I could not verify, and why

- **No live API call was made**, by instruction. Every claim about this cluster's behaviour is documentary, or drawn from the two repos' own recorded evidence. The token question is therefore genuinely open, which is why section 7.4 exists.
- **`bpg`'s VMID allocation path when `vm_id` is unset** is inferred from strings in a compiled binary, not from reading the Go source. Section 7.5 states the risk and the cheap defence. **Low confidence, and the thing in this document most likely to be wrong.**
- **The unbaked template has never been built here.** The claim that an unbooted template needs no seal follows from how cloud images are constructed, and this repo has the test that would falsify it, but the test has not been run against an unbaked template.
- **The `.img` versus `.qcow2` extension rule** points opposite ways in this repo's evidence and in `bpg`'s documentation, and the difference appears to sit at a PVE version boundary around 8.4. I could not adjudicate without a live call. Test it; assume neither direction.
- **Packer** was checked and is not recommended, so it was not exercised. Its documentation confirms token authentication is supported (*"Either `password` or `token` must be specifed. If both are set, `token` takes precedence."*) and that its communicator targets the guest rather than the node, so it would not break containment. It is moot once the bake is deleted, since the bake was the only thing it would have replaced.
- **I did not evaluate whether the target node is a sound host for a month-long stateful run.** The estate repo raises that about itself and the user has knowingly accepted the risk. Not a provisioning question.

---

## 13. Register entries this creates, contradicts or retires

Stated explicitly rather than talked past, per the standing rule. **I am not editing the register**; these are the rows to fold in.

| Entry | Status after this document |
|---|---|
| 2026-08-24 (archive), Terraform rejected, with "`bpg/proxmox` if Terraform is ever revisited" | **This is the sanctioned revisit, and it reverses the rejection, conditionally.** The Telmate / `VM.Monitor` reason never applied to `bpg`. The state-file reason is weaker than stated (reconstructible for four resources) but real as a leak class. |
| 2026-09-08, "No shared provisioning library extracted yet; extract when a second project is named" | **Upheld and discharged, not overturned.** See section 2. Adopting an externally maintained provider is not the extraction that row declines. |
| 2026-08-27, guest packages baked over SSH, rejecting `cicustom` | **Conclusion upheld, reason now verified from Proxmox's own source rather than inferred. The whole entry becomes moot** if the bake is deleted per section 4. |
| 2026-08-27, the bake takes a static build address from `DF_BUILD_IP` | **Retired.** Its premise, needing SSH before the agent exists, disappears with the bake. |
| 2026-08-27, the bake verifies `/agent/ping` and seals before conversion | **Retired as code, retained as a condition.** Never convert a booted VM to a template without sealing. |
| 2026-08-27 and 2026-08-28, vmid-derived MACs and `DF_MAC_OVERRIDES` | **Retired**, per the prior spec's section 3, whose addressing recommendation this document depends on. |
| 2026-08-27, agent command endpoints are POST, info endpoints are GET | **Retained as prose.** The code that needed it goes; the misleading error does not. |
| 2026-08-28, `cpu: host` becomes `x86-64-v2-AES`, accepted, not yet implemented | **Folded in**, as a declared attribute rather than a manual step. |
| 2026-08-27, `next_vmid()` is the only safe source of a vmid | **At risk under the new tool.** See 7.5. |
| New | Snippets cannot be uploaded through the PVE API at all: `enum => ['iso','vztmpl','import']` on both `upload` and `download_url`, read from `pve-storage.git`. |
| New | `ciupgrade` and `arch` are `root@pam`-only parameters, unreachable by any pool-scoped token, the same class as the `migration_type` restriction the estate repo already records. |
| New | Ansible's own documentation contradicts itself on WSL as a control node: the installation guide lists it as supported, the Windows OS guide says it should not be used for production. Recorded so the point is not re-litigated from one page. |
| New | The PVE `download-url` checksum parameters are spelled `checksum` and `checksum-algorithm`, confirmed from two independent primary sources. Usable in `pve.py` today, regardless of the layer 2 outcome. |
