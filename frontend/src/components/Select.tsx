import { useId } from "react";

const label = (value: string) => value.replace(/_/g, " ");

/** Labelled dropdown with an "any" option that maps to an empty string. */
export function Select(props: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
}) {
  // Explicit for/id: some screen readers ignore a wrapping <label> and read only "Any".
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{props.label}</label>
      <select id={id} value={props.value} onChange={(e) => props.onChange(e.target.value)}>
        <option value="">Any {props.label.toLowerCase()}</option>
        {props.options.map((option) => (
          <option key={option} value={option}>
            {label(option)}
          </option>
        ))}
      </select>
    </div>
  );
}
