# @mihailorama/enrichfold

Provider-neutral, offline-first company identity gates for TypeScript. This
package makes no network calls and owns no credentials, storage, or outreach.

```ts
import { deriveCompanyIdentity } from "@mihailorama/enrichfold";

const identity = deriveCompanyIdentity({
  email: "hello@acme.example",
  companyName: "Acme",
  website: "https://acme.example",
});

if (identity.status === "verified") {
  // The host application can decide whether to proceed.
}
```

`needs_review` is a deliberate, safe result: retain the returned reason and
ask an application-level reviewer to approve any next action.

## License

MIT.
