# Mail sign-in rules for Google and Microsoft

**Checked:** October 20, 2026 (written by an outside helper, brief O3). **Sources verified by the main session on October 21, 2026:** every quoted sentence was found on its page, except that for the consent-policy page only the mention of `Mail.Read` was confirmed, not the exact exclusion wording. This is a point-in-time reading of the official pages linked below. A quote is the exact sentence or table wording the answer rests on.

## Google

### 1. Testing users, removing users, and the lifetime cap

Testing projects allow up to 100 test users. Google says a test user spends project test-user quota “once added,” so removing an address should not be assumed to free a place; the page does not explicitly state the deletion behavior. Separately, an unverified app requesting sensitive or restricted scopes has a cap of 100 new users over the project's lifetime. That lifetime quota cannot be reset. These are two related but distinct limits.

**Sources (read October 20, 2026):**

- [OAuth app state overview](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview?authuser=9&hl=en) — “Only users explicitly added to the test user allowlist can access the app (limited to a hard cap of 100 test users).”
- [Manage App Audience](https://support.google.com/cloud/answer/15549945?hl=en-MC) — “A test user consumes a project's test user quota once added to the project.”
- [Frequently Asked Questions](https://support.google.com/cloud/answer/13463817?hl=en-uk) — “Please note the user cap applies over the entire lifetime of the project, and it cannot be reset or changed.”

### 2. Seven-day expiration in Testing

Yes. For an External project in Testing, the refresh token expires after seven days if the app requests any scope beyond the basic identity-only set (name, email, profile). Gmail read scopes are outside that exception, so a Gmail reader must expect recurring authorization. The official guidance says the user's authorization also expires after seven days; this is not merely a refresh-token housekeeping detail.

**Sources (read October 20, 2026):**

- [Using OAuth 2.0 to Access Google APIs](https://developers.google.com/identity/protocols/oauth2/) — “A Google Cloud Platform project with an OAuth consent screen configured for an external user type and a publishing status of \"Testing\" is issued a refresh token expiring in 7 days, unless the only OAuth scopes requested are a subset of name, email address, and user profile.”
- [Manage App Audience](https://support.google.com/cloud/answer/15549945?hl=en-MC) — “If your app requests any other OAuth scopes, then this exception does not apply.”

### 3. Moving a one-person, self-registered Gmail reader to In production

If this is genuinely a personal-use app—only its maker, or a few people personally known to the maker, use it—Google lists personal use as an exception to submitting for verification. Owning the OAuth project does not itself create the exception; the actual audience and use do. `gmail.readonly` is a restricted scope. If the app is published without approval for that scope, the person should still expect Google's “Google hasn't verified this app” warning before consent and must choose to continue through it. In Testing they instead see the test-app warning, and the seven-day expiry from question 2 remains. Moving to In production removes the test-user-list requirement, but it does not turn an unverified restricted scope into a verified one.

**Sources (read October 20, 2026):**

- [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification) — “If your app is going to be used in any of the scenarios described in the following sections, you don't need to submit it for review.”
- [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification) — “One use case is if you are the only user of your app or if your app is used by only a few users, all of whom are known personally to you.”
- [Choose Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) — “`https://www.googleapis.com/auth/gmail.readonly`” is listed under “Restricted scopes.”
- [Unverified apps](https://support.google.com/cloud/answer/7454865?hl=en&ref_topic=3473162) — “The app or script might display an \"unverified app\" screen before it displays the consent screen.”

### 4. Annual security assessment, cost, and the local-app/AI-service design

For a restricted-scope app in the verification process, Google may require an annual CASA security assessment by an independent, Google-empanelled assessor. Google's help page estimates six weeks for restricted-scope verification, including the assessment step; this is an estimate, not a promise. Google itself charges no assessment fee. It says an assessor sets the price with the developer. One assessor, TAC Security, currently publishes CASA plans from **$675 to $5,400**: its listed packages vary by assurance level, retesting, support, and included services, so this is a vendor's menu, not a Google-wide price range. Google also describes a free Tier 2 self-assessment path for some apps; the app's assigned tier and route should be confirmed in the project's verification flow.

Local-only storage does not settle the question if the app sends Gmail text to an AI service. Google's Gmail scope page says transmitting restricted-scope data triggers an assessment. That makes a desktop app that sends the text to a provider's server look in scope for the public product. I found no official statement addressing the precise case where the user chooses and pays for that AI service. Do not assume a personal AI account exempts the app. Separately, Google's current Workspace data policy says AI use must be limited to a personalized model for the user's requested feature; the user's own billing account does not, by itself, establish that the model is “personalized.”

**Sources (read October 20, 2026):**

- [Choose Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) — “If you store restricted scope data on servers (or transmit), then you must go through a security assessment.”
- [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification) — “Every app that requests access to Google users' restricted data and has the ability to access data from or through a third-party server must go through a security assessment from Google-empanelled security assessors.”
- [Google security assessment FAQ](https://support.google.com/cloud/answer/13463817?hl=en-uk) — “Google does not charge the developer any fees for security assessment.”
- [Google security assessment FAQ](https://support.google.com/cloud/answer/13463817?hl=en-uk) — “The cost for such a service is agreed on between the developer and the assessor without any involvement from Google.”
- [Google security assessment FAQ](https://support.google.com/cloud/answer/13463817?hl=en-uk) — “If you are in scope for the free tier 2 assessment and choose to reachout to the authorized assessors you will be required to pay the authorized assessor directly.”
- [Google security assessment FAQ](https://support.google.com/cloud/answer/13463817?hl=en-uk) — “In general, the security assessment must be done once a year.”
- [TAC Security's CASA pricing](https://tacsecurity.com/google-casa-cloud-application-security-assessment/) — its published plan prices include “$675,” “$855,” “$4500,” and “$5400.”
- [Google security assessment FAQ](https://support.google.com/cloud/answer/13463817?hl=en-uk) — “Google User Data must be used only for a personalized model to execute a user-facing feature or the user-directed appropriate use case.”

### 5. App passwords for personal Gmail and Google Workspace

**Personal Gmail:** app passwords are still documented and available for eligible accounts with 2-Step Verification. They are a legacy fallback, not the preferred sign-in, and can be unavailable when the account uses security keys only or Advanced Protection.

**Google Workspace:** ordinary username-and-password access by third-party mail apps ended May 1, 2025; OAuth is the supported route. Workspace's current help still documents app passwords for users who need 2-Step Verification with older clients, while the general Gmail help says managed work or school accounts might not have the app-password option. Therefore app passwords are not universally gone, but whether a Workspace user can use one depends on account and administrator settings. They are not a sound product-wide fallback.

**Sources (read October 20, 2026):**

- [Sign in with app passwords](https://support.google.com/mail/answer/185833?hl=en) — “To create an app password, you need 2-Step Verification on your Google Account.”
- [Sign in with app passwords](https://support.google.com/mail/answer/185833?hl=en) — “You're logged into a work, school, or another organization account.” (listed as one reason the option might be unavailable)
- [Set up Gmail with a third-party email client](https://knowledge.workspace.google.com/admin/sync/set-up-gmail-with-a-third-party-email-client?hl=en) — “Starting May 1, 2025, Google Workspace accounts no longer support less secure apps, third-party apps, or devices that ask you to sign in to your Google Account with your username and password.”
- [Set up Gmail with a third-party email client](https://knowledge.workspace.google.com/admin/sync/set-up-gmail-with-a-third-party-email-client?hl=en) — “These users need application-specific passwords to access the mail client.”

## Microsoft

### 6. Personal Outlook.com over IMAP

IMAP still works for a personal Outlook.com account if IMAP is enabled, but it must use OAuth 2.0 / Modern Auth. Do not plan on collecting the user's Microsoft password or using an app password as the IMAP authentication mechanism. Microsoft's settings page has a general note that an app password may be needed for some devices, but the same page's IMAP row explicitly says `OAuth2/Modern Auth`; Microsoft's developer instructions confirm OAuth support for Outlook.com. The password/app-password wording is not a clear exception for an app implementing IMAP itself.

**Sources (read October 20, 2026):**

- [POP, IMAP, and SMTP settings for Outlook.com](https://support.microsoft.com/en-us/outlook/pop-imap-and-smtp-settings-for-outlook-com) — “Outlook.com requires the use of Modern Auth / OAuth2.”
- [Authenticate an IMAP, POP or SMTP connection using OAuth](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth) — “OAuth2 support for IMAP, POP, and SMTP protocols as described below is available for both Microsoft 365 (which includes Office on the web) and Outlook.com users.”
- [POP, IMAP, and SMTP settings for Outlook.com](https://support.microsoft.com/en-us/outlook/pop-imap-and-smtp-settings-for-outlook-com) — the IMAP table lists “Authentication Method | OAuth2/Modern Auth.”

### 7. Microsoft publisher verification

Publisher verification is chiefly for multitenant apps requesting OAuth permissions across other organizations. To get it, the publisher needs a verified Microsoft AI Cloud Partner Program account and Partner ID, an Entra tenant associated with that partner account, a publisher domain, authorized roles, and multifactor authentication. A `.onmicrosoft.com` domain cannot be the verified publisher domain. Microsoft charges **$0** for publisher verification and says no license is required. If an eligible cross-tenant app is unverified, users can see an “unverified publisher” warning; where the tenant's risk-based consent controls apply, users may be blocked from consenting. A Microsoft consumer account used to register the app cannot be used for publisher verification.

**Sources (read October 20, 2026):**

- [Mark an app as publisher verified](https://learn.microsoft.com/en-us/entra/identity-platform/mark-app-as-publisher-verified) — “When an app registration has a verified publisher, it means that the publisher of the app has verified their identity using their Microsoft AI Cloud Partner Program account and has associated this account with their app registration.”
- [Publisher verification overview](https://learn.microsoft.com/en-us/entra/identity-platform/publisher-verification-overview) — “The developer must have a Partner One ID for a valid Microsoft AI Cloud Partner Program account that has completed the verification process.”
- [Publisher verification overview](https://learn.microsoft.com/en-us/entra/identity-platform/publisher-verification-overview) — “Apps that are registered by using a Microsoft account can't be publisher verified.”
- [Publisher verification overview](https://learn.microsoft.com/en-us/entra/identity-platform/publisher-verification-overview) — “No charges are associated with completing the prerequisites for publisher verification.”
- [Publisher verification overview](https://learn.microsoft.com/en-us/entra/identity-platform/publisher-verification-overview) — “Microsoft doesn't charge developers for publisher verification.”
- [Publisher verification overview](https://learn.microsoft.com/en-us/entra/identity-platform/publisher-verification-overview) — “The warning informs the user that the app was created by an unverified publisher and that the app is risky to download or install.”

### 8. Consent for a person's own registration

Microsoft identity app registrations live in an Entra tenant; a personal Microsoft account can be selected as a supported sign-in audience, but it is not itself a separate app-registration store. The app maker can register an app in a tenant and allow personal Microsoft accounts, work accounts, or both, subject to the supported-account setting.

For a personal Outlook.com user, Graph's delegated `Mail.Read` and `Calendars.Read` are available for consent in personal Microsoft accounts. The first consent normally shows the app identity and a “Permissions requested” list describing the requested access. The user grants it for their own mailbox and calendar. If permissions were already granted, no new dialog is required unless the app asks for additional permissions.

For a company account, `Mail.Read` and `Calendars.Read` are technically marked as delegated permissions that do not inherently require admin consent. However, Microsoft's default recommended user-consent policy currently excludes those mail and calendar permissions for ordinary users. So the company admin may need to approve the app or grant tenant-wide consent. Admin consent shows “Accept for your organization”; after an admin grants consent, users in that tenant generally do not see another consent dialog unless the app asks for new permissions. The person creating their own app registration in a company tenant does not override that tenant's consent policy unless they also have a suitable administrator role.

If the app also requests write or send permissions, those appear separately and can trigger different tenant-policy results. A personal test registration is not the same as consent for a shared, public app.

**Sources (read October 20, 2026):**

- [Create a Microsoft Entra tenant](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-create-new-tenant) — “To build an environment for either work and school accounts or personal Microsoft accounts (MSA), you can use an existing Microsoft Entra tenant or create a new one.”
- [Single and multitenant apps](https://learn.microsoft.com/en-us/entra/identity-platform/single-and-multi-tenant-apps) — “All users with a work or school, or personal Microsoft account can use your application or API.”
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference?view=graph-rest-1.0) — for delegated `Mail.Read`, “The Mail.Read delegated permission is available for consent in personal Microsoft accounts.”
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference?view=graph-rest-1.0) — for delegated `Calendars.Read`, “The Calendars.Read delegated permission is available for consent in personal Microsoft accounts.”
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference?view=graph-rest-1.0) — the `Mail.Read` delegated permission has “AdminConsentRequired | No.”
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference?view=graph-rest-1.0) — the `Calendars.Read` delegated permission has “AdminConsentRequired | No.”
- [Manage app consent policies](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/manage-app-consent-policies) — “This is also the default for a new tenant.”
- [Manage app consent policies](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/manage-app-consent-policies) — the current policy excludes “`Mail.Read`” and “`Calendars.Read`” from ordinary end-user consent.
- [Consent experience for applications](https://learn.microsoft.com/en-us/entra/identity-platform/application-consent-experience) — “In user consent flow, the title is \"Permissions requested\” while in the admin consent flow the title has another line \"Accept for your organization.\”
- [Consent experience for applications](https://learn.microsoft.com/en-us/entra/identity-platform/application-consent-experience) — “All users in that tenant don't see the consent dialog unless the application requires new permissions.”

## Not confirmed

- Google does not explicitly say on the audience page whether deleting a test-user entry returns that particular allowlist slot. Its “once added” wording argues against assuming it does. The separate 100-new-user lifetime cap is explicit.
- Google does not publish one universal CASA price. Its pages allow a free self-assessment route for some tiers and say assessors set their own fees. TAC's published prices are one provider's packages, not a required Google fee schedule.
- No official Google page I found says whether a desktop app that sends mail text to the user's separately chosen AI provider is treated differently from an app that operates its own server. The Gmail page's “store ... or transmit” wording points toward assessment; the exact architecture should be put to Google during the verification process.
- No official Google page says that a user's own account with an AI provider makes a shared foundation model “personalized.” The Workspace policy defines personalized models by their exclusive scope to that user or organization and by not mixing users' data.
- Microsoft's Outlook.com setup page mentions an app password in general prose, but its IMAP authentication table specifies OAuth. I found no current Microsoft statement that app passwords work as direct IMAP credentials for a newly built client.
- The exact company consent prompt depends on that tenant's configuration, the user's role, permissions already granted, and whether an admin approval workflow is enabled. The wording above describes Microsoft's documented common paths, not a guarantee for every tenant.
