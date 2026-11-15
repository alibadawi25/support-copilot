const label = (value: string) => value.replace(/_/g, " ");

/** Labelled dropdown with an "any" option that maps to an empty string. */
export function Select(props: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="field">
      <span>{props.label}</span>
      <select value={props.value} onChange={(e) => props.onChange(e.target.value)}>
        <option value="">Any</option>
        {props.options.map((option) => (
          <option key={option} value={option}>
            {label(option)}
          </option>
        ))}
      </select>
    </label>
  );
}
