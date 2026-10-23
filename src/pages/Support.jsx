import AppHeader from "@/components/AppHeader";
import { useBackToHome } from "@/hooks/useBackToHome";

export default function Support() {
  useBackToHome();
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <AppHeader title="Customer Support" variant="public" maxWidth="3xl" />

      <div className="max-w-3xl mx-auto px-6 py-12 space-y-10">
        <div>
          <h1 className="font-fredoka text-4xl text-primary mb-2">Customer Support</h1>
          <p className="text-muted-foreground text-sm">Last updated: August 2026</p>
        </div>

        <section className="space-y-4">
          <h2 className="font-fredoka text-2xl text-foreground">Get in Touch</h2>
          <p className="text-sm leading-relaxed text-foreground/80">
            We're here to help! If you have any questions, feedback, or issues with Teacher Translate, please reach out to us and we'll get back to you as soon as possible.
          </p>
          <div className="bg-white rounded-2xl border border-border p-5 space-y-3">
            <div className="flex items-start gap-3">
              <span className="text-2xl">📧</span>
              <div>
                <p className="font-bold text-sm">Email Support</p>
                <a href="mailto:support@teachertranslate.com.au" className="text-primary text-sm underline">
                  support@teachertranslate.com.au
                </a>
                <p className="text-xs text-muted-foreground mt-1">We aim to respond within 1–2 business days.</p>
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-4">
          <h2 className="font-fredoka text-2xl text-foreground">Frequently Asked Questions</h2>

          <div className="space-y-4">
            {[
            {
              q: "How does Teacher Translate work?",
              a: "You upload or paste a teacher's report comment, and our AI decodes it into plain English — explaining what it really means and how your child is tracking against the Australian Curriculum."
            },
            {
              q: "How many free scans do I get?",
              a: "Every new account gets 3 free scans to try the service. After that, you can subscribe to Pro for unlimited scans and access to year level assessments and curriculum-linked activity suggestions."
            },
            {
              q: "How much does a Pro subscription cost?",
              a: "Pro is $14.95 AUD for your first year, then $29.95 AUD per year. Your subscription renews automatically each year and can be cancelled at any time."
            },
            {
              q: "How do I cancel my subscription?",
              a: `You can cancel your subscription at any time by deleting your account (from the settings menu). You can also cancel your subscription by emailing us at <a href="mailto:support@teachertranslate.com.au" class="text-primary underline">support@teachertranslate.com.au</a> using the same email account that was used to register your account with. We'll cancel your subscription promptly and you'll retain access until the end of your billing period. 14 days prior to your renewal date, you will receive an email to remind you of your pending account deletion.`
            },
            {
              q: "Is my data secure?",
              a: "Yes. All data is encrypted in transit and at rest. We do not share your report content or personal information with third parties. Please see our Privacy Policy for full details."
            },
            {
              q: "What year levels are supported?",
              a: "Teacher Translate supports all Australian school year levels from Kindergarten / Foundation / Prep through to Year 12, across all states and territories by referencing the Australian Curriculum (Version 9.0). Please note that Victoria, New South Wales and Western Australia use their own interpretations of the Australian Curriculum. Teacher Translate does not factor for these variances."
            },
            {
              q: "Can I use it for multiple children?",
              a: 'Yes! You can create separate student profiles for each of your children within your account and track their progress year to year. Please see our <a href="https://teachertranslate.com.au/terms" class="text-primary underline">reasonable use policy</a>.'
            }].
            map(({ q, a }, i) =>
            <div key={i} className="bg-white rounded-2xl border border-border p-5">
                <p className="font-bold text-sm mb-1">{q}</p>
                <p className="text-sm text-foreground/80 leading-relaxed" dangerouslySetInnerHTML={{ __html: a }} />
              </div>
            )}
          </div>
        </section>

        <section className="space-y-4">
          <h2 className="font-fredoka text-2xl text-foreground">Refunds</h2>
          <p className="text-sm leading-relaxed text-foreground/80">
            If you're not satisfied with your subscription, contact us within 14 days of your purchase at{" "}
            <a href="mailto:support@teachertranslate.com.au" className="text-primary underline">
              support@teachertranslate.com.au
            </a>{" "}
            from the same email account as Teacher Translate account, detailing the reason for your dissatisfaction, and we'll arrange a full refund.
          </p>
        </section>

        <section>
          <h2 className="font-fredoka text-2xl text-foreground mb-4">App versions</h2>
          <p className="text-sm leading-relaxed text-foreground/80 mb-1">
            <strong>Version 1.8</strong>
          </p>
          <p className="text-sm leading-relaxed text-foreground/80 mb-0">New features:</p>
          <ul className="list-disc pl-5 space-y-1 text-sm text-foreground/80 mt-0.5">
            <li>Security update</li>
            <li>Improved history tracking</li>
          </ul>
          <p className="text-sm leading-relaxed text-foreground/80 mt-8 mb-1">
            <strong>Version 1.7</strong>
          </p>
          <p className="text-sm leading-relaxed text-foreground/80 mb-0">New features:</p>
          <ul className="list-disc pl-5 space-y-1 text-sm text-foreground/80 mt-0.5">
            <li>Idded swipe functionality between translation modes</li>
            <li>Improved app navigation</li>
          </ul>
          <p className="text-sm leading-relaxed text-foreground/80 mt-8 mb-1">
            <strong>Version 1.6</strong>
          </p>
          <p className="text-sm leading-relaxed text-foreground/80 mb-0">New features:</p>
          <ul className="list-disc pl-5 space-y-1 text-sm text-foreground/80 mt-0.5">
            <li>Improved cosmetic changes</li>
            <li>Improved camera function</li>
          </ul>
          <p className="text-sm leading-relaxed text-foreground/80 mt-8 mb-1">
            <strong>Version 1.5</strong>
          </p>
          <p className="text-sm leading-relaxed text-foreground/80 mb-0">New features:</p>
          <ul className="list-disc pl-5 space-y-1 text-sm text-foreground/80 mt-0.5">
            <li>Added "Hilarious" mode</li>
            <li>Improved localised language</li>
          </ul>
          <p className="text-sm leading-relaxed text-foreground/80 mt-8 mb-1">
            <strong>Version 1.4</strong>
          </p>
          <p className="text-sm leading-relaxed text-foreground/80 mb-0">New features:</p>
          <ul className="list-disc pl-5 space-y-1 text-sm text-foreground/80 mt-0.5">
            <li>Improved translation details</li>
            <li>Added year expectations</li>
            <li>Added glossary of frequent terms</li>
          </ul>
        </section>

        <footer className="border-t border-border pt-8 text-center text-xs text-muted-foreground space-y-1">
          <p>© {new Date().getFullYear()} Teacher Translate · <a href="https://www.teachertranslate.com.au" className="underline">www.teachertranslate.com.au</a></p>
          <p className="space-x-3">
            <a href="/terms" className="underline">Terms of Use</a>
            <span>·</span>
            <a href="/privacy" className="underline">Privacy Policy</a>
          </p>
        </footer>
      </div>
    </div>);

}