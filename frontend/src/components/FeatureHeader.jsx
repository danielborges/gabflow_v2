export function FeatureHeader({
  eyebrow,
  title,
  description,
  icon: Icon,
  className = "",
  contained = false,
  children,
}) {
  const classes = [
    "feature-header",
    contained ? "feature-header-contained" : "",
    className,
  ].filter(Boolean).join(" ");

  return (
    <header className={classes}>
      <div className="feature-header-copy">
        <p className="eyebrow">{eyebrow}</p>
        <div className="feature-header-title">
          <h1>
            {Icon && <Icon className="feature-header-icon" size={26} aria-hidden="true" />}
            {title}
          </h1>
        </div>
        {description && <p className="feature-header-description">{description}</p>}
      </div>
      {children}
    </header>
  );
}
