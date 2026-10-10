# Published conversion outputs

This repository includes the `final_task/` package and compact `review/` records for four current runs:

| Task | Runtime | Published package |
| --- | --- | --- |
| `instance_qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f34c` | Python | `final_task/` |
| `instance_element-hq__element-web-776ffa47641c7ec6d142ab4a47691c30ebf83c2e` | JavaScript | `final_task/` |
| `instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b` | TypeScript | `final_task/` |
| `instance_navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e` | Go | `final_task/` |

Each package was published by the pipeline after its recorded gates and smoke check; `review/progress.json` records `PACKAGED`. These artifacts are historical results. The later validation boundary in [the main README](../README.md#current-validation-boundary) still applies: fresh cross-language Docker validation is incomplete, and the Tutanota synthetic DOM/runtime shim issue remains open. Package publication does not establish that broader guarantee.

`source/`, `intermediate/`, archived runs, model traces, caches, and local secrets are not part of this Git snapshot. The `review/` files document the included outputs.
