"use client";

import { useState } from "react";
import { api } from "../lib/api";

const DIMS = [
  ["correctness", "Correctness"],
  ["relevance", "Relevance"],
  ["completeness", "Completeness"],
  ["usefulness", "Usefulness"],
];

export default function FeedbackWidget({ eventId }) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState({ correctness: 3, relevance: 3, completeness: 3, usefulness: 3 });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  if (result) {
    return (
      <p className="muted" role="status">
        Thanks — feedback recorded
        {result.scored ? " and used to score this answer." : "; it will be used once enough signal exists."}
      </p>
    );
  }
  if (!open) return <button onClick={() => setOpen(true)}>Rate this answer</button>;
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setError("");
        try {
          setResult(await api(`/api/v1/events/${eventId}/feedback`, { method: "POST", body: values }));
        } catch (err) {
          setError(err.message);
        }
      }}
    >
      {DIMS.map(([key, label]) => (
        <div key={key}>
          <label htmlFor={`fb-${eventId}-${key}`}>{label}: {values[key]}</label>
          <input
            id={`fb-${eventId}-${key}`}
            type="range"
            min="1"
            max="5"
            step="1"
            value={values[key]}
            onChange={(e) => setValues({ ...values, [key]: Number(e.target.value) })}
          />
        </div>
      ))}
      <p role="alert" className="error">{error}</p>
      <div className="row">
        <button className="primary" type="submit">Submit</button>
        <button type="button" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </form>
  );
}
