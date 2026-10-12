import { api } from "../api.js";
import { money, Progress, StatusBadge } from "../format.jsx";
import useApiData from "./useApiData.js";

function initials(name) {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export default function Investors({ version }) {
  const { data, error, loading } = useApiData(api.investors, version);

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
                  <th>Investor</th>
                  <th className="num">Total called</th>
                  <th className="num">Funded</th>
                  <th className="num">Remaining</th>
                  <th className="col-progress">Progress</th>
                  <th>Payment status</th>
                </tr>
              </thead>
              <tbody>
                {data.map((i) => (
                  <tr key={i.id}>
                    <td>
                      <div className="person">
                        <div className="person-avatar">{initials(i.name)}</div>
                        <div>
                          <div className="strong">{i.name}</div>
                          <div className="muted small">{i.email}</div>
                        </div>
                      </div>
                    </td>
                    <td className="num">{money(i.total_called)}</td>
                    <td className="num">{money(i.total_funded)}</td>
                    <td className="num strong">{money(i.remaining_balance)}</td>
                    <td className="col-progress">
                      <Progress value={i.total_funded} total={i.total_called} />
                    </td>
                    <td>
                      <StatusBadge status={i.payment_status} />
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
