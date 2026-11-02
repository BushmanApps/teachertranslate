import { useSearchParams } from "react-router-dom";
import AppHeader from "@/components/AppHeader";
import { useBackToHome } from "@/hooks/useBackToHome";

export default function Privacy() {
  // When opened from the consent screen, back returns there instead of home.
  const [searchParams] = useSearchParams();
  useBackToHome(searchParams.get("from") === "consent" ? "/consent" : "/");
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <AppHeader title="Privacy Policy" variant="public" maxWidth="3xl" />

      <div className="max-w-3xl mx-auto px-6 py-12 space-y-10">
        <div>
          <h1 className="font-fredoka text-4xl text-primary mb-2">Privacy Policy</h1>
          <p className="text-muted-foreground text-sm">Last updated: July 2026</p>
        </div>

        <p className="text-sm leading-relaxed text-foreground/80">
          Teacher Translate ("we", "our", or "us") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, and safeguard your personal information when you use our service at{" "}
          <a href="https://www.teachertranslate.com.au" className="text-primary underline" target="_blank">www.teachertranslate.com.au</a>.
        </p>

        {[
          {
            title: "1. Information We Collect",
            content: (
              <ul className="list-disc pl-5 space-y-2 text-sm text-foreground/80">
                <li><strong>Account information:</strong> Your email address when you register.</li>
                <li><strong>Student profile data:</strong> Year levels and optional student names you provide to personalise results.</li>
                <li><strong>Report content:</strong> The teacher comment text (report) you submit for translation. This is processed by our AI and stored so you can access your history.</li>
                <li><strong>Usage data:</strong> Number of scans used, subscription status, and timestamps of activity.</li>
                <li><strong>Payment information:</strong> Payments are handled securely by Apple App Store or Google Play. We do not store your payment card details.</li>
              </ul>
            )
          },
          {
            title: "2. How We Use Your Information",
            content: (
              <ul className="list-disc pl-5 space-y-2 text-sm text-foreground/80">
                <li>To provide and improve the Teacher Translate service.</li>
                <li>To process your report text and generate AI translations.</li>
                <li>To manage your account, subscription, and billing.</li>
                <li>To send transactional emails (e.g. receipts, account updates).</li>
                <li>Only <strong>anonymised and aggregated</strong> data (all personal attributes removed) may be used to improve AI models. AI-model training is not among the processing purposes for identifiable personal data. More information can be found in the <a href="https://base44.com/dpa" target="_blank" className="text-primary underline">Data Processing Agreement</a>, specifically at points 2.3.5 and 3.1</li>
              </ul>
            )
          },
          {
            title: "3. Data Storage and Security",
            content: (
              <div className="space-y-3">
                <p className="text-sm leading-relaxed text-foreground/80">
                  Your data is stored securely on servers located in the United States (Base44 platform) with industry-standard encryption in transit (TLS) and at rest. We implement appropriate technical and organisational measures to protect your data against unauthorised access, loss, or disclosure.
                </p>
                <p className="text-sm leading-relaxed text-foreground/80">
                  Pro users can delete translations at any time from the History section (Trial user's translations are not saved).
                </p>
              </div>
            )
          },
          {
            title: "4. Children's Privacy",
            content: (
              <div className="space-y-3">
                <p className="text-sm leading-relaxed text-foreground/80">
                  Teacher Translate is intended for use by parents and guardians. A first name can be included to help the user conveniently organise reports. A year level is required to allow accurate matching of student performance and appropriate recommendations of support.
                </p>
                <p className="text-sm leading-relaxed text-foreground/80">
                  We do not knowingly collect personal data directly from children. If you believe a child has provided personal data without parental consent, please contact us and we will delete it promptly.
                </p>
                <p className="text-sm leading-relaxed text-foreground/80">
                  If you have concerns about identification from the uploaded report, Teacher Translate recommends you copy your teacher's comments into a new document and upload this as a PDF, anonymising the upload from details such as school and teacher name. Additionally, you may use aliases for your child(ren) or leave this information blank.
                </p>
                <p className="text-sm leading-relaxed text-foreground/80">
                  Teacher Translate does not pass on identifiable content to third parties for AI model training.
                </p>
              </div>
            )
          },
          {
            title: "5. Data Retention",
            content: (
              <p className="text-sm leading-relaxed text-foreground/80">
                We retain your account data and translation history for as long as your account is active. You may delete your account from the settings menu. This will immediately remove your data stored with us. The only retained information is your email address and number of scans utilised, for the purpose of avoiding multiple free use of the service. You may request deletion of your data at any time by emailing{" "}
                <a href="mailto:support@teachertranslate.com.au" className="text-primary underline">support@teachertranslate.com.au</a> from the same email account as used in your registration to Teacher Translate.
                We will delete your data within 30 days of such a request.
              </p>
            )
          },
          {
            title: "6. App Permissions",
            content: (
              <div className="space-y-3">
                <p className="text-sm leading-relaxed text-foreground/80">
                  Teacher Translate only utilises the following permissions:
                </p>
                <ul className="list-disc pl-5 space-y-2 text-sm text-foreground/80">
                  <li><strong>Access the internet:</strong> to upload reports and receive your translations.</li>
                  <li><strong>Check your network connection:</strong> to know when you're online and avoid failed uploads.</li>
                  <li><strong>Use your Wi-Fi:</strong> to check your Wi-Fi connection status for reliable uploads.</li>
                  <li><strong>Camera (optional):</strong> to scan a paper report with your camera. You can upload a file or type text instead.</li>
                  <li><strong>Internal app messaging:</strong> lets parts of the app communicate privately with each other; no other apps can use it nor can users message each other through the app.</li>
                </ul>
                <p className="text-sm leading-relaxed text-foreground/80">
                  Teacher Translate does <strong>not</strong> utilise other permissions such as access to your contacts, location, calendar, microphone, phone calls, Bluetooth, NFC, or your photos and files storage, nor any other permissions not listed above.
                </p>
              </div>
            )
          },
          {
            title: "7. Third-Party Services",
            content: (
              <ul className="list-disc pl-5 space-y-2 text-sm text-foreground/80">
                <li><strong>Apple App Store and Google Play:</strong> Used to process subscriptions securely under their respective privacy policies.</li>
                <li><strong>Gemini / AI models:</strong> Report text is sent to AI providers for translation.</li>
                <li><strong>Base44:</strong> The platform powering our backend infrastructure.</li>
              </ul>
            )
          },
          {
            title: "8. Your Rights",
            content: (
              <ul className="list-disc pl-5 space-y-2 text-sm text-foreground/80">
                <li>Access the personal information we hold about you.</li>
                <li>Request correction of inaccurate data.</li>
                <li>Request deletion of your account and data.</li>
                <li>Withdraw consent at any time (which may affect your ability to use the service).</li>
                <li>To exercise any of these rights, email us at <a href="mailto:support@teachertranslate.com.au" className="text-primary underline">support@teachertranslate.com.au</a>.</li>
              </ul>
            )
          },
          {
            title: "9. Cookies",
            content: (
              <p className="text-sm leading-relaxed text-foreground/80">
                We use essential cookies and local storage to keep you logged in, to remember your preferences and for analytics purposes. We do not use advertising cookies.
              </p>
            )
          },
          {
            title: "10. Changes to This Policy",
            content: (
              <p className="text-sm leading-relaxed text-foreground/80">
                We may update this Privacy Policy from time to time. We will notify you of significant changes by posting the new policy on this page with an updated date. Continued use of the service after changes constitutes acceptance of the updated policy.
              </p>
            )
          },
          {
            title: "11. Contact Us",
            content: (
              <p className="text-sm leading-relaxed text-foreground/80">
                If you have any questions about this Privacy Policy, please contact us at:{" "}
                <a href="mailto:support@teachertranslate.com.au" className="text-primary underline">support@teachertranslate.com.au</a>
              </p>
            )
          }
        ].map(({ title, content }, i) => (
          <section key={i} className="space-y-3">
            <h2 className="font-fredoka text-xl text-foreground">{title}</h2>
            {content}
          </section>
        ))}

        <footer className="border-t border-border pt-8 text-center text-xs text-muted-foreground space-y-1">
          <p>© {new Date().getFullYear()} Teacher Translate · <a href="https://www.teachertranslate.com.au" className="underline" target="_blank">www.teachertranslate.com.au</a></p>
          <p className="space-x-3">
            <a href="/support" className="underline">Customer Support</a>
            <span>·</span>
            <a href="/terms" className="underline">Terms of Use</a>
          </p>
        </footer>
      </div>
    </div>
  );
}