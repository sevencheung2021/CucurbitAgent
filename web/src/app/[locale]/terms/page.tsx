import { Link } from '@/i18n/routing';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Terms of Use · CucurbitAgent',
  description: 'How the CucurbitAgent research platform may be used.',
};

const TERMS_VERSION = 'v1.0';
const TERMS_UPDATED = '2026-07-29';
const CONTACT_EMAIL = 'bvrc@nercv.org';

function H2({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mt-8 mb-3 text-lg font-bold text-[#0F766E] first:mt-0">{children}</h2>
  );
}

export default function TermsPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-10 text-slate-800">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[#0F766E]">Terms of Use</h1>
        <p className="mt-2 text-sm text-slate-500">
          Version {TERMS_VERSION} · Last updated {TERMS_UPDATED}
        </p>
      </div>

      <div className="space-y-1 text-sm leading-relaxed">
        <p>
          These Terms govern your use of the CucurbitAgent platform (&ldquo;the Service&rdquo;), operated
          by the Beijing Vegetable Research Center (BVRC), Beijing Academy of Agriculture and
          Forestry Sciences (BAAFS). The Service is provided free of charge for academic research.
          By registering or using the Service you agree to these Terms and to our{' '}
          <Link href="/privacy" className="font-medium text-[#0D9488] underline">
            Privacy Policy
          </Link>
          .
        </p>

        <H2>1. Your Account</H2>
        <p>
          You register with your email address; sign-in is by a one-time code sent to that address —
          there is no password. You are responsible for keeping access to your email account and for
          all activity performed under your identity.
        </p>

        <H2>2. Acceptable Use</H2>
        <p>The Service is intended for non-commercial academic research. You agree to:</p>
        <ul className="my-2 list-disc space-y-1.5 pl-5">
          <li>Use it only for lawful research and educational purposes.</li>
          <li>
            Not submit confidential, classified, or third-party-proprietary data that you do not have
            the right to process.
          </li>
          <li>
            Not attempt to overload, disrupt, reverse-engineer, or gain unauthorised access to the
            Service or its underlying data.
          </li>
          <li>Respect applicable intellectual-property and data-protection laws.</li>
        </ul>

        <H2>3. AI-Generated Content</H2>
        <p>
          Answers from the CucurbitAgent assistant are produced by AI models and may contain errors or
          outdated information. They are{' '}
          <strong className="text-slate-900">not professional or scientific advice</strong> and must
          be independently verified before being relied upon for publication, breeding decisions, or
          any consequential work.
        </p>

        <H2>4. Data and Privacy</H2>
        <p>
          What we collect and why is described in our{' '}
          <Link href="/privacy" className="font-medium text-[#0D9488] underline">
            Privacy Policy
          </Link>
          .
        </p>

        <H2>5. Intellectual Property</H2>
        <p>
          Integrated datasets, annotations, and structures remain the property of their respective
          rights holders, and third-party data is subject to its original licences. You retain
          ownership of the queries you submit; by submitting them you grant us a non-exclusive licence
          to process them solely to operate and improve the Service, as described in the Privacy
          Policy.
        </p>

        <H2>6. Availability</H2>
        <p>
          The Service is provided on a best-effort, &ldquo;as-is&rdquo; basis, without warranties of
          any kind. We may modify, suspend, or discontinue features, or apply rate limits, at any
          time, and accept no liability for any resulting loss.
        </p>

        <H2>7. Changes to These Terms</H2>
        <p>
          We may revise these Terms by updating the version and date above. Material changes will be
          presented for re-acceptance on your next sign-in where required.
        </p>

        <H2>8. Governing Law</H2>
        <p>
          These Terms are governed by the laws of the People&rsquo;s Republic of China.
        </p>

        <H2>9. Contact</H2>
        <p>
          Questions about these Terms? Email{' '}
          <a href={`mailto:${CONTACT_EMAIL}`} className="font-medium text-[#0D9488] underline">
            {CONTACT_EMAIL}
          </a>
          .
        </p>

        <div className="mt-10 flex items-center justify-between border-t border-slate-200 pt-4 text-sm">
          <Link href="/privacy" className="text-[#0D9488] hover:underline">
            ← Privacy Policy
          </Link>
          <Link href="/" className="text-[#0D9488] hover:underline">
            Back to home →
          </Link>
        </div>
      </div>
    </div>
  );
}
