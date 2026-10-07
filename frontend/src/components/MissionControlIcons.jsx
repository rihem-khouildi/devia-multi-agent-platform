const strokeProps = {
  fill: "none",
  stroke: "currentColor",
  strokeLinecap: "round",
  strokeLinejoin: "round",
  strokeWidth: 1.8,
}

function IconBase({ children, className = "h-5 w-5" }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      {children}
    </svg>
  )
}

export function MissionControlGlyph({ name, className }) {
  const icons = {
    stories: (
      <IconBase className={className}>
        <path {...strokeProps} d="M6 4.75h8.5a3.75 3.75 0 0 1 3.75 3.75V19.25H9.5A3.5 3.5 0 0 0 6 22V4.75Z" />
        <path {...strokeProps} d="M6 4.75H5A2.25 2.25 0 0 0 2.75 7v12.5A1.75 1.75 0 0 0 4.5 21.25H6" />
        <path {...strokeProps} d="M9.5 9h5M9.5 12.5h5M9.5 16h3.25" />
      </IconBase>
    ),
    graph: (
      <IconBase className={className}>
        <circle {...strokeProps} cx="6" cy="12" r="2.5" />
        <circle {...strokeProps} cx="18" cy="7" r="2.5" />
        <circle {...strokeProps} cx="18" cy="17" r="2.5" />
        <path {...strokeProps} d="M8.3 10.9 15.7 8.1M8.3 13.1l7.4 2.8" />
      </IconBase>
    ),
    run: (
      <IconBase className={className}>
        <path {...strokeProps} d="M12 3.75A8.25 8.25 0 1 0 20.25 12" />
        <path {...strokeProps} d="M12 7.25v5l3.5 2" />
        <path {...strokeProps} d="M14.75 3.75h5.5v5.5" />
      </IconBase>
    ),
    shield: (
      <IconBase className={className}>
        <path {...strokeProps} d="M12 3.5 5.75 6v5.5c0 4.25 2.82 8.1 6.25 9 3.43-.9 6.25-4.75 6.25-9V6L12 3.5Z" />
        <path {...strokeProps} d="m9.5 12 1.75 1.75L15 10" />
      </IconBase>
    ),
    launch: (
      <IconBase className={className}>
        <path {...strokeProps} d="m14.5 9.5 0-4.75 4.75 0" />
        <path {...strokeProps} d="M19.25 4.75 10.75 13.25" />
        <path {...strokeProps} d="M11 5.75H8A3.25 3.25 0 0 0 4.75 9v7A3.25 3.25 0 0 0 8 19.25h7A3.25 3.25 0 0 0 18.25 16v-3" />
      </IconBase>
    ),
    bell: (
      <IconBase className={className}>
        <path {...strokeProps} d="M6.75 9.75a5.25 5.25 0 1 1 10.5 0c0 5.25 2 6.5 2 6.5h-14.5s2-1.25 2-6.5" />
        <path {...strokeProps} d="M10 18.25a2 2 0 0 0 4 0" />
      </IconBase>
    ),
    help: (
      <IconBase className={className}>
        <circle {...strokeProps} cx="12" cy="12" r="8.25" />
        <path {...strokeProps} d="M9.8 9.2a2.4 2.4 0 1 1 4.28 1.5c-.78 1-.98 1.3-.98 2.3" />
        <path {...strokeProps} d="M12 16.65h.01" />
      </IconBase>
    ),
    success: (
      <IconBase className={className}>
        <circle {...strokeProps} cx="12" cy="12" r="8.25" />
        <path {...strokeProps} d="m8.75 12.1 2.15 2.15 4.35-4.5" />
      </IconBase>
    ),
    warning: (
      <IconBase className={className}>
        <path {...strokeProps} d="M10.97 4.74 3.9 17a1.4 1.4 0 0 0 1.21 2.1h14.18A1.4 1.4 0 0 0 20.5 17L13.43 4.74a1.4 1.4 0 0 0-2.46 0Z" />
        <path {...strokeProps} d="M12 9v4.5M12 16.5h.01" />
      </IconBase>
    ),
    failed: (
      <IconBase className={className}>
        <circle {...strokeProps} cx="12" cy="12" r="8.25" />
        <path {...strokeProps} d="m9 9 6 6M15 9l-6 6" />
      </IconBase>
    ),
    blocked: (
      <IconBase className={className}>
        <circle {...strokeProps} cx="12" cy="12" r="8.25" />
        <path {...strokeProps} d="M8.5 12h7" />
      </IconBase>
    ),
    running: (
      <IconBase className={className}>
        <circle {...strokeProps} cx="12" cy="12" r="8.25" />
        <path {...strokeProps} d="M12 7.75V12l3 1.75" />
      </IconBase>
    ),
    pending: (
      <IconBase className={className}>
        <circle {...strokeProps} cx="12" cy="12" r="8.25" />
        <path {...strokeProps} d="M8.5 12h7" />
      </IconBase>
    ),
    file: (
      <IconBase className={className}>
        <path {...strokeProps} d="M8 3.75h5.5l4.75 4.75V20.25H8a2.25 2.25 0 0 1-2.25-2.25V6A2.25 2.25 0 0 1 8 3.75Z" />
        <path {...strokeProps} d="M13.5 3.75v4.75h4.75M9.5 13h5M9.5 16h5" />
      </IconBase>
    ),
    sparkle: (
      <IconBase className={className}>
        <path {...strokeProps} d="M12 3.5v4.25M12 16.25V20.5M3.5 12h4.25M16.25 12H20.5" />
        <path {...strokeProps} d="m6.75 6.75 2.5 2.5M14.75 14.75l2.5 2.5M6.75 17.25l2.5-2.5M14.75 9.25l2.5-2.5" />
      </IconBase>
    ),
    lock: (
      <IconBase className={className}>
        <rect {...strokeProps} x="5.25" y="10.5" width="13.5" height="9.25" rx="2.25" />
        <path {...strokeProps} d="M8.25 10.5V8a3.75 3.75 0 0 1 7.5 0v2.5" />
        <path {...strokeProps} d="M12 14v2.25" />
      </IconBase>
    ),
    replay: (
      <IconBase className={className}>
        <path {...strokeProps} d="M4.5 12a7.5 7.5 0 1 0 2.4-5.5" />
        <path {...strokeProps} d="M4.5 4.5v3.75h3.75" />
      </IconBase>
    ),
    brain: (
      <IconBase className={className}>
        <path {...strokeProps} d="M9.5 4.75A2.75 2.75 0 0 0 6.75 7.5v.65a2.75 2.75 0 0 0-1.5 4.85 2.75 2.75 0 0 0 1.5 4.85v.65A2.75 2.75 0 0 0 9.5 21.25V4.75Z" />
        <path {...strokeProps} d="M14.5 4.75a2.75 2.75 0 0 1 2.75 2.75v.65a2.75 2.75 0 0 1 1.5 4.85 2.75 2.75 0 0 1-1.5 4.85v.65a2.75 2.75 0 0 1-2.75 2.75V4.75Z" />
        <path {...strokeProps} d="M9.5 9.5h2M14.5 9.5h-2M9.5 14.5h2M14.5 14.5h-2" />
      </IconBase>
    ),
    target: (
      <IconBase className={className}>
        <circle {...strokeProps} cx="12" cy="12" r="8.25" />
        <circle {...strokeProps} cx="12" cy="12" r="4.5" />
        <circle {...strokeProps} cx="12" cy="12" r="1.25" />
      </IconBase>
    ),
    arrow: (
      <IconBase className={className}>
        <path {...strokeProps} d="M4.5 12h14.5" />
        <path {...strokeProps} d="m13 6 6 6-6 6" />
      </IconBase>
    ),
    book: (
      <IconBase className={className}>
        <path {...strokeProps} d="M5 5.25h6.5a3 3 0 0 1 3 3v11a2 2 0 0 0-2-2H5V5.25Z" />
        <path {...strokeProps} d="M19 5.25h-6.5a3 3 0 0 0-3 3v11a2 2 0 0 1 2-2H19V5.25Z" />
      </IconBase>
    ),
    github: (
      <IconBase className={className}>
        <path {...strokeProps} d="M12 3.75a8.25 8.25 0 0 0-2.6 16.08c.4.07.55-.18.55-.4v-1.4c-2.3.5-2.78-1.1-2.78-1.1-.38-.95-.92-1.2-.92-1.2-.75-.5.06-.5.06-.5.83.06 1.27.85 1.27.85.74 1.27 1.94.9 2.41.7.07-.55.29-.9.52-1.1-1.84-.2-3.77-.92-3.77-4.1 0-.92.32-1.66.86-2.24-.09-.21-.37-1.06.08-2.21 0 0 .7-.22 2.3.85a8 8 0 0 1 4.18 0c1.6-1.07 2.3-.85 2.3-.85.45 1.15.17 2 .08 2.21.54.58.86 1.32.86 2.24 0 3.19-1.94 3.9-3.78 4.1.3.26.56.76.56 1.54v2.28c0 .22.15.48.55.4A8.25 8.25 0 0 0 12 3.75Z" />
      </IconBase>
    ),
    coverage: (
      <IconBase className={className}>
        <circle {...strokeProps} cx="12" cy="12" r="8.25" />
        <path {...strokeProps} d="M3.75 12A8.25 8.25 0 0 1 12 3.75v8.25H3.75Z" />
      </IconBase>
    ),
  }

  return icons[name] || icons.file
}
