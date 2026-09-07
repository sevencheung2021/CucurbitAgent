export default function About({ title, paragraphs }: { title: string; paragraphs: string[] }) {
  return (
    <section className="max-w-content mx-auto px-4 my-12 text-center">
      <h2 className="text-teal-brand font-bold text-2xl mb-4">{title}</h2>
      <div className="text-[#334155] text-base leading-relaxed text-justify space-y-4">
        {paragraphs.map((p, i) => (
          <p key={i} className="indent-8">{p}</p>
        ))}
      </div>
    </section>
  );
}
