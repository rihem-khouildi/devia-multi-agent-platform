export default function SectionCard({ children, className = "" }) {
  return (
    <div
      className={`surface-card rounded-[28px] ${className}`}
    >
      {children}
    </div>
  )
}
