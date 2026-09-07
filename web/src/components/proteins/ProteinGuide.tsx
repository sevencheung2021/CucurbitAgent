export default function ProteinGuide() {
  const cards = [
    ['🖱️', 'Rotate & Zoom', 'Left-click to rotate. Scroll to zoom.'],
    ['🔘', 'Identify Sites', 'Click any residue for site info.'],
    ['🎨', 'Confidence Coloring', 'Red/Orange = Low. Blue = High.'],
  ];
  return (
    <div className="mt-6 grid gap-5 rounded-xl border border-[#eee] bg-white p-5 md:grid-cols-3">
      {cards.map(([icon, title, text], i) => (
        <div key={title} className={`text-center ${i === 1 ? 'md:border-x md:border-[#eee]' : ''}`}>
          <div className="mb-2 text-2xl">{icon}</div>
          <div className="text-sm font-bold text-[#34495e]">{title}</div>
          <div className="text-xs text-[#95a5a6]">{text}</div>
        </div>
      ))}
    </div>
  );
}
