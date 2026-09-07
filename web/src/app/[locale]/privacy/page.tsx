import { Link } from '@/i18n/routing';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Privacy Policy · CucurbitAgent',
  description: 'What CucurbitAgent collects and why.',
};

const POLICY_VERSION = 'v1.0';
const POLICY_UPDATED = '2026-07-29';
const CONTACT_EMAIL = 'bvrc@nercv.org';

function H2({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mt-8 mb-3 text-lg font-bold text-[#0F766E] first:mt-0">{children}</h2>
  );
}

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-10 text-slate-800">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[#0F766E]">Privacy Policy</h1>
        <p className="mt-2 text-sm text-slate-500">
          Version {POLICY_VERSION} · Last updated {POLICY_UPDATED}
        </p>
      </div>

      <div className="space-y-1 text-sm leading-relaxed">
        <p>
          CucurbitAgent is a non-commercial research platform operated by the{' '}
          <strong className="text-slate-900">Beijing Vegetable Research Center (BVRC)</strong>,
          Beijing Academy of Agriculture and Forestry Sciences (BAAFS). We collect as little
          information as possible — only what is needed to verify you are a real person, keep the
          service running, and fix problems when they occur.{' '}
          <strong className="text-slate-900">
            We do not collect passwords, do not track you across other sites, and do not sell or
            share your data.
          </strong>
        </p>

        <H2>1. What We Collect</H2>
        <p>Only the following:</p>
        <ul className="my-2 list-disc space-y-1.5 pl-5">
          <li>
            <strong className="text-slate-900">Email address</strong> — used solely to verify that
            you are a real person. Sign-in is by a one-time code sent to your email; we never ask
            for or store a password.
          </li>
          <li>
            <strong className="text-slate-900">Professional role</strong> — the category you select
            at registration (e.g. researcher, student), for our records only.
          </li>
          <li>
            <strong className="text-slate-900">Search and query records</strong> — when you look up
            a gene, run an analysis, or ask the CucurbitAgent assistant a question, the text of your query
            is logged together with your user ID and a hashed IP address. This is used to reproduce
            and diagnose problems and to understand which features are used.
          </li>
          <li>
            <strong className="text-slate-900">Error logs</strong> — server-side error and diagnostic
            messages generated while you use the platform, used solely to find and fix bugs.
          </li>
          <li>
            <strong className="text-slate-900">Feedback you choose to submit</strong> — anything you
            enter on the Feedback page. We only record this when you actively submit it.
          </li>
        </ul>
        <p>
          For technical integrity only, verification codes and session tokens are stored as salted
          cryptographic hashes (not plaintext) and are deleted shortly after use. To display the
          aggregate visitor statistics in the site footer, an approximate country is derived from
          your IP address and stored as a hash; the raw IP is not retained.
        </p>

        <H2>2. Why We Collect It</H2>
        <ul className="my-2 list-disc space-y-1.5 pl-5">
          <li>To confirm you are a real person and to keep you signed in.</li>
          <li>To reproduce, investigate, and fix errors you encounter.</li>
          <li>To understand which modules are useful and to improve the platform.</li>
          <li>To respond when you contact us or submit feedback.</li>
        </ul>

        <H2>3. The AI Assistant</H2>
        <p>
          When you ask the CucurbitAgent assistant a question, your query text is sent to our AI model
          provider (Zhipu AI) in order to generate a response. This is the only situation in which
          your input leaves our servers. Apart from this, your information is not shared with any
          third party.
        </p>

        <H2>4. How Long We Keep It</H2>
        <ul className="my-2 list-disc space-y-1.5 pl-5">
          <li>One-time sign-in codes: deleted immediately after use or after 10 minutes.</li>
          <li>Sessions: expire after 30 days of inactivity.</li>
          <li>Search / query logs and error logs: kept for up to 90 days, then deleted.</li>
          <li>
            Your email, role, and feedback: kept for as long as your account exists, and deleted on
            request.
          </li>
        </ul>

        <H2>5. Security</H2>
        <p>
          No passwords are stored. Codes and tokens are stored only as salted hashes. Data is hosted
          on institutionally controlled servers. As with any online service, absolute security cannot
          be guaranteed.
        </p>

        <H2>6. Your Rights</H2>
        <p>
          You may request access to, correction of, or deletion of the information we hold about you,
          and you may withdraw your consent at any time (which will close your account). To do so,
          email{' '}
          <a href={`mailto:${CONTACT_EMAIL}`} className="font-medium text-[#0D9488] underline">
            {CONTACT_EMAIL}
          </a>
          .
        </p>

        <H2>7. Changes to This Policy</H2>
        <p>
          If this policy is updated, the version and date above will change. Where a change is
          material we will ask for your agreement again the next time you sign in.
        </p>

        <H2>8. Contact</H2>
        <p>
          Questions about your data? Email{' '}
          <a href={`mailto:${CONTACT_EMAIL}`} className="font-medium text-[#0D9488] underline">
            {CONTACT_EMAIL}
          </a>
          , or write to:
          <br />
          Beijing Vegetable Research Center (BVRC), BAAFS
          <br />
          No. 50 Zhanghua Road, Haidian District, Beijing, China
        </p>

        <div className="mt-10 flex items-center justify-between border-t border-slate-200 pt-4 text-sm">
          <Link href="/" className="text-[#0D9488] hover:underline">
            ← Back to home
          </Link>
          <Link href="/terms" className="text-[#0D9488] hover:underline">
            Terms of Use →
          </Link>
        </div>
      </div>
    </div>
  );
}
