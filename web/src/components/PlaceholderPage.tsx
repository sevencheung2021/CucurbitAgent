export default function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <div className="max-w-content mx-auto px-4 py-16 text-center">
      <h1 className="text-3xl font-bold text-teal-brand mb-4">{title}</h1>
      <p className="text-slate-muted max-w-xl mx-auto">{description}</p>
      <p className="text-sm text-slate-card mt-6">Phase 2: migrating from v28 Streamlit module.</p>
    </div>
  );
}
