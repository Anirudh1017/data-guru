interface Props {
  columns: string[];
  rows: (string | number)[][];
}

export default function ResultsTable({ columns, rows }: Props) {
  if (!columns.length) return null;
  if (!rows.length) return <div className="empty">No records matched. Try a different commodity or state.</div>;
  return (
    <div className="card">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{r.map((cell, j) => <td key={j}>{cell}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
