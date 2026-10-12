import { api } from "../api.js";
import { money, Progress, shortDate, StatusBadge } from "../format.jsx";
import useApiData from "./useApiData.js";

export default function CapitalCalls({ version }) {
  const { data, error, loading } = useApiData(api.capitalCalls, version);

  return (
    <section className="card card-flush">
      {error && <div className="alert alert-error">{error}</div>}
      {loading && !data ? (
        <div className="skeleton-list pad">
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      ) : (
        data && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Investor</th>
                  <th>Issued</th>
                  <th>Due</th>
                  <th className="num">Called</th>
                  <th className="num">Funded</th>
                  <th className="num">Remaining</th>
                  <th className="col-progress">Progress</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <span className="ref-pill">{c.reference}</span>
                    </td>
                    <td className="strong">{c.investor_name}</td>
                    <td className="nowrap muted">{shortDate(c.call_date)}</td>
                    <td className="nowrap muted">{shortDate(c.due_date)}</td>
                    <td className="num">{money(c.amount_called)}</td>
                    <td className="num">{money(c.amount_funded)}</td>
                    <td className="num strong">{money(c.remaining_amount)}</td>
                    <td className="col-progress">
                      <Progress value={c.amount_funded} total={c.amount_called} />
                    </td>
                    <td>
                      <StatusBadge status={c.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </section>
  );
}
