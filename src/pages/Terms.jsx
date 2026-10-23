import { useSearchParams } from "react-router-dom";
import AppHeader from "@/components/AppHeader";
import { useBackToHome } from "@/hooks/useBackToHome";

export default function Terms() {
  // When opened from the consent screen, back returns there instead of home.
  const [searchParams] = useSearchParams();
  useBackToHome(searchParams.get("from") === "consent" ? "/consent" : "/");
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <AppHeader title="Terms of Use" variant="public" maxWidth="3xl" />

      <div className="max-w-3xl mx-auto px-6 py-12 space-y-10">
        <div>
          <h1 className="font-fredoka text-4xl text-primary mb-2">Terms of Use</h1>
          <p className="text-muted-foreground text-sm">Last updated: July 2026</p>
        </div>

        <p className="text-sm leading-relaxed text-foreground/80">
          Please read these Terms of Service carefully before using Teacher Translate. By accessing or using our service, you agree to be bound by these terms. If you do not agree, please do not use the service.
        </p>

        {[
        {
          title: "1. About the Service",
          content:
          <p className="text-sm leading-relaxed text-foreground/80">
                Teacher Translate is an AI-powered tool that helps parents and guardians interpret school report comments into plain English. It is available at{" "}
                <a href="https://www.teachertranslate.com.au" className="text-primary underline" target="blank">www.teachertranslate.com.au</a>.
              </p>

        },
        {
          title: "2. Eligibility",
          content:
          <p className="text-sm leading-relaxed text-foreground/80">
                You must be at least 18 years of age to use Teacher Translate. By using the service, you represent that you are 18 or older and have the legal capacity to enter into these Terms.
                You must have legal authority to view and share any documents uploaded or scanned by this service.
              </p>

        },
        {
          title: "3. Your Account",
          content:
          <ul className="list-disc pl-5 space-y-2 text-sm text-foreground/80">
                <li>You are responsible for maintaining the confidentiality of your account credentials.</li>
                <li>You are responsible for all activity that occurs under your account.</li>
                <li>You must notify us immediately at <a href="mailto:support@teachertranslate.com.au" className="text-primary underline">support@teachertranslate.com.au</a> if you suspect unauthorised access to your account.</li>
                <li>We reserve the right to suspend or terminate accounts that violate these Terms.</li>
              </ul>

        },
        {
          title: "4. Free Trial and Subscriptions",
          content:
          <ul className="list-disc pl-5 space-y-2 text-sm text-foreground/80">
                <li>New accounts receive 3 free scans to trial the service.</li>
                <li>Pro subscriptions are charged at <strong>$14.95 AUD</strong> for the first year and <strong>$29.95 AUD</strong> per year thereafter.</li>
                <li>Subscriptions renew automatically on an annual basis unless cancelled.</li>
                <li>You may cancel at any time by deleting your account (from the settings menu) or by contacting us at <a href="mailto:support@teachertranslate.com.au" className="text-primary underline">support@teachertranslate.com.au</a> from the same email account as your account is registered with.</li>
                <li>No refunds are issued for partial subscription periods, except within our 14-day satisfaction guarantee (see Section 5).</li>
                <li>All prices are in Australian Dollars (AUD) and inclusive of GST where applicable.</li>
              </ul>

        },
        {
          title: "5. Refund Policy",
          content:
          <div className="space-y-3">
                <p className="text-sm leading-relaxed text-foreground/80">
                  If you are not satisfied with your Pro subscription, you may request a full refund within 14 days of your initial purchase by contacting us at{" "}
                  <a href="mailto:support@teachertranslate.com.au" className="text-primary underline">support@teachertranslate.com.au</a> from the same email account as your Teacher Translate account, detailing the reason for your dissatisfaction.
                </p>
                <p className="text-sm leading-relaxed text-foreground/80">Deleting your account within the 14-day satisfaction guarantee period does not automate a refund of your subscription.</p>
                <p className="text-sm leading-relaxed text-foreground/80">Only one trial period per account is permitted (regardless of Pro subscription status).</p>
              </div>

        },
        {
          title: "6. Acceptable Use",
          content:
          <>
                <p className="text-sm leading-relaxed text-foreground/80 mb-2">You agree not to:</p>
                <ul className="list-disc pl-5 space-y-2 text-sm text-foreground/80">
                  <li>Use the service for any unlawful purpose.</li>
                  <li>Upload content that is offensive, defamatory, or infringes third-party rights.</li>
                  <li>Attempt to reverse-engineer, scrape, or copy our AI outputs for commercial purposes.</li>
                  <li>Share your account access with others or resell access to the service.</li>
                  <li>Attempt to disrupt or interfere with the security or integrity of the service.</li>
                </ul>
              </>

        },
        {
          title: "7. Reasonable Use",
          content:
          <>
                <p className="text-sm leading-relaxed text-foreground/80 mb-2">You agree to:</p>
                <ul className="list-disc pl-5 space-y-2 text-sm text-foreground/80">
                  <li>Use the service for personal and individual use only and not on behalf of others. This includes but is not limited to social, parent or networking groups, teacher cohorts, schools or others.</li>
                </ul>
                <p className="text-sm leading-relaxed text-foreground/80 mb-2"> Teacher Translate may scan usage data to determine if abuse of the service constitutes a breach of the above (excessive use), which may result in the suspension or termination of your account, without a refund payable.
                </p>
                </>

        },
        {
          title: "7. AI-Generated Content Disclaimer",
          content:
          <p className="text-sm leading-relaxed text-foreground/80">
                Teacher Translate uses artificial intelligence to interpret teacher report comments. The translations and assessments provided are for informational purposes only and should not be relied upon as professional, educational or psychological advice. Results may not always be accurate. We recommend discussing any concerns about your child's progress directly with their teacher. We accept no liability for decisions made based on AI-generated content.
              </p>

        },
        {
          title: "8. Intellectual Property",
          content:
          <p className="text-sm leading-relaxed text-foreground/80">
                All content, branding, and technology on Teacher Translate is owned by or licensed to us. You retain ownership of the report content you submit. By submitting content, you grant us a limited licence to process it solely for the purpose of providing the service to you.
              </p>

        },
        {
          title: "10. Limitation of Liability",
          content:
          <div className="space-y-3">
                <p className="text-sm leading-relaxed text-foreground/80">
                  Teacher Translate is not liable for any misrepresentations of a child or their learning. This disclaimer is clearly displayed during the translation process and at the end of every translated report. By using this service, you acknowledge that you have read, understood and agree with this disclaimer.
                </p>
                <p className="text-sm leading-relaxed text-foreground/80">
                  To the maximum extent permitted by Australian law, Teacher Translate is not liable for any indirect, incidental, special, or consequential damages arising from your use of the service. Our total liability to you for any claim is limited to the amount you paid us in the 12 months preceding the claim.
                </p>
              </div>

        },
        {
          title: "11. Privacy",
          content:
          <p className="text-sm leading-relaxed text-foreground/80">
                Your use of Teacher Translate is also governed by our{" "}
                <a href="/privacy" className="text-primary underline">Privacy Policy</a>, which is incorporated into these Terms by reference.
              </p>

        },
        {
          title: "12. Changes to These Terms",
          content:
          <p className="text-sm leading-relaxed text-foreground/80">
                We may update these Terms from time to time. We will notify you of material changes by posting the updated Terms on this page with a revised date. Your continued use of the service after changes constitutes acceptance of the new Terms.
              </p>

        },
        {
          title: "13. Governing Law",
          content:
          <p className="text-sm leading-relaxed text-foreground/80">
                These Terms are governed by the laws of New South Wales, Australia. Any disputes will be subject to the exclusive jurisdiction of the courts of New South Wales.
              </p>

        },
        {
          title: "14. Contact",
          content:
          <p className="text-sm leading-relaxed text-foreground/80">
                For any questions about these Terms, please contact us at:{" "}
                <a href="mailto:support@teachertranslate.com.au" className="text-primary underline">support@teachertranslate.com.au</a>
              </p>

        }].
        map(({ title, content }, i) =>
        <section key={i} className="space-y-3">
            <h2 className="font-fredoka text-xl text-foreground">{title}</h2>
            {content}
          </section>
        )}

        <footer className="border-t border-border pt-8 text-center text-xs text-muted-foreground space-y-1">
          <p>© {new Date().getFullYear()} Teacher Translate · <a href="https://www.teachertranslate.com.au" className="underline" target="blank">www.teachertranslate.com.au</a></p>
          <p className="space-x-3">
            <a href="/support" className="underline">Customer Support</a>
            <span>·</span>
            <a href="/privacy" className="underline">Privacy Policy</a>
          </p>
        </footer>
      </div>
    </div>);

}