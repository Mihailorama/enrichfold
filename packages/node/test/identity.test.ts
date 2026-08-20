import { describe, expect, test } from "bun:test";
import { deriveCompanyIdentity } from "../src/index.ts";

describe("deriveCompanyIdentity", () => {
  test("verifies an exact company-domain match", () => {
    expect(
      deriveCompanyIdentity({
        email: "hello@acme.example",
        companyName: "Acme",
        website: "https://www.acme.example/about",
      }),
    ).toMatchObject({
      status: "verified",
      canonicalDomain: "acme.example",
      reason: "matching_email_and_website",
    });
  });

  test("fails closed for a free mailbox with an arbitrary website", () => {
    expect(
      deriveCompanyIdentity({
        email: "person@gmail.com",
        companyName: "Acme",
        website: "https://acme.example",
      }),
    ).toMatchObject({
      status: "needs_review",
      reason: "free_email_with_unverified_website",
    });
  });

  test("supports caller-specific placeholder names", () => {
    expect(
      deriveCompanyIdentity({
        email: "person@acme.example",
        companyName: "Компания",
        website: null,
        genericCompanyNames: ["компания"],
      }),
    ).toMatchObject({
      status: "needs_review",
      name: null,
      reason: "missing_company_name",
    });
  });

  test("does not accept a corporate domain that only contains the brand name", () => {
    expect(
      deriveCompanyIdentity({
        email: "press@adidas-deals.com",
        companyName: "Adidas",
        website: null,
      }),
    ).toMatchObject({
      status: "needs_review",
      reason: "corporate_email_domain_unverified",
    });
  });
});
