/** Provider-neutral, offline-first company identity gates for TypeScript. */

export const DEFAULT_FREE_EMAIL_DOMAINS = new Set([
  "gmail.com",
  "googlemail.com",
  "mail.ru",
  "inbox.ru",
  "list.ru",
  "bk.ru",
  "yandex.ru",
  "ya.ru",
  "outlook.com",
  "hotmail.com",
  "icloud.com",
  "proton.me",
  "protonmail.com",
  "yahoo.com",
]);

export const DEFAULT_GENERIC_COMPANY_NAMES = new Set([
  "company",
  "unknown company",
  "unknown",
]);

export type SiteIdentity = {
  name: string;
  domain: string;
};

export type CompanyIdentity = {
  status: "verified" | "needs_review";
  name: string | null;
  canonicalDomain: string | null;
  website: string | null;
  slug: string | null;
  reason:
    | "missing_company_name"
    | "invalid_email"
    | "invalid_website"
    | "free_email_without_website"
    | "free_email_with_unverified_website"
    | "corporate_email_domain_unverified"
    | "corporate_email_domain"
    | "corporate_email_domain_site_metadata"
    | "matching_email_and_website"
    | "domain_conflict";
};

export type CompanyIdentityInput = {
  email: string;
  companyName: string | null | undefined;
  website: string | null | undefined;
  verifiedSiteIdentity?: SiteIdentity | null;
  freeEmailDomains?: Iterable<string>;
  genericCompanyNames?: Iterable<string>;
};

const DOMAIN_PATTERN = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i;

function normalizedSet(values: Iterable<string>): Set<string> {
  return new Set([...values].map((value) => value.trim().toLocaleLowerCase("en-US")));
}

function identity(
  status: CompanyIdentity["status"],
  name: string | null,
  domain: string | null,
  slug: string | null,
  reason: CompanyIdentity["reason"],
): CompanyIdentity {
  return {
    status,
    name,
    canonicalDomain: domain,
    website: domain ? `https://${domain}` : null,
    slug,
    reason,
  };
}

export function companyEmailDomain(email: string): string | null {
  const trimmed = email.trim().toLocaleLowerCase("en-US");
  const at = trimmed.lastIndexOf("@");
  const domain = at > 0 ? trimmed.slice(at + 1) : "";
  return DOMAIN_PATTERN.test(domain) ? domain : null;
}

export function canonicalWebsiteDomain(website: string | null | undefined): string | null {
  if (!website?.trim()) return null;
  try {
    const value = /^https?:\/\//i.test(website) ? website : `https://${website}`;
    const parsed = new URL(value);
    const hostname = parsed.hostname.toLocaleLowerCase("en-US").replace(/^www\./, "");
    return ["http:", "https:"].includes(parsed.protocol) && DOMAIN_PATTERN.test(hostname)
      ? hostname
      : null;
  } catch {
    return null;
  }
}

export function isFreeEmailDomain(domain: string, domains: Iterable<string> = DEFAULT_FREE_EMAIL_DOMAINS): boolean {
  return normalizedSet(domains).has(domain.toLocaleLowerCase("en-US"));
}

export function isGenericCompanyName(name: string | null | undefined, names: Iterable<string> = DEFAULT_GENERIC_COMPANY_NAMES): boolean {
  const normalized = (name ?? "").trim().replace(/\s+/g, " ").toLocaleLowerCase("en-US");
  return !normalized || normalizedSet(names).has(normalized);
}

export function slugify(value: string): string {
  return value
    .trim()
    .toLocaleLowerCase("en-US")
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "");
}

function domainsMatch(left: string, right: string): boolean {
  return left === right || left.endsWith(`.${right}`) || right.endsWith(`.${left}`);
}

export function companyNameMatchesDomain(name: string, domain: string): boolean {
  const labels = domain.toLocaleLowerCase("en-US").replace(/^www\./, "").split(".");
  if (labels.length !== 2) return false;
  const normalizedName = name.toLocaleLowerCase("en-US").replace(/[^a-z0-9]/g, "");
  return Boolean(normalizedName) && normalizedName === labels[0].replace(/-/g, "");
}

/**
 * Derive a company identity without I/O. The result is review-first: an
 * application should auto-act only on a `verified` result and preserve `reason`.
 */
export function deriveCompanyIdentity(input: CompanyIdentityInput): CompanyIdentity {
  const genericNames = new Set([
    ...DEFAULT_GENERIC_COMPANY_NAMES,
    ...(input.genericCompanyNames ?? []),
  ]);
  const name = isGenericCompanyName(input.companyName, genericNames)
    ? null
    : input.companyName!.trim();
  const slug = name ? slugify(name) : null;
  const emailDomain = companyEmailDomain(input.email);
  const websiteDomain = canonicalWebsiteDomain(input.website);
  const freeDomains = new Set([
    ...DEFAULT_FREE_EMAIL_DOMAINS,
    ...(input.freeEmailDomains ?? []),
  ]);

  if (!name || !slug) return identity("needs_review", null, websiteDomain ?? emailDomain, null, "missing_company_name");
  if (!emailDomain) return identity("needs_review", name, websiteDomain, slug, "invalid_email");
  if (input.website?.trim() && !websiteDomain) return identity("needs_review", name, null, slug, "invalid_website");
  if (websiteDomain && !isFreeEmailDomain(emailDomain, freeDomains) && !domainsMatch(emailDomain, websiteDomain)) {
    return identity("needs_review", name, websiteDomain, slug, "domain_conflict");
  }
  if (websiteDomain && isFreeEmailDomain(emailDomain, freeDomains)) {
    return identity("needs_review", name, websiteDomain, slug, "free_email_with_unverified_website");
  }
  const verified = input.verifiedSiteIdentity;
  if (
    websiteDomain
    && verified?.name.trim() === name
    && domainsMatch(websiteDomain, verified.domain.toLocaleLowerCase("en-US").replace(/^www\./, ""))
  ) {
    return identity("verified", name, websiteDomain, slug, "corporate_email_domain_site_metadata");
  }
  if (websiteDomain && companyNameMatchesDomain(name, websiteDomain)) {
    return identity("verified", name, websiteDomain, slug, "matching_email_and_website");
  }
  if (websiteDomain) return identity("needs_review", name, websiteDomain, slug, "corporate_email_domain_unverified");
  if (isFreeEmailDomain(emailDomain, freeDomains)) {
    return identity("needs_review", name, null, slug, "free_email_without_website");
  }
  if (companyNameMatchesDomain(name, emailDomain)) {
    return identity("verified", name, emailDomain, slug, "corporate_email_domain");
  }
  return identity("needs_review", name, emailDomain, slug, "corporate_email_domain_unverified");
}
