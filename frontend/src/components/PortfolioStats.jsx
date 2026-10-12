import { api } from "../api.js";
import { money } from "../format.jsx";
import useApiData from "./useApiData.js";

export default function PortfolioStats({ version }) {
  const { data } = useApiData(api.capitalCalls, version);
  if (!data) return <div className="kpis kpis-loading" />;

  const called = data.reduce((sum, c) => sum + Number(c.amount_called), 0);
  const funded = data.reduce((sum, c) => sum + Number(c.amount_funded), 0);
  const outstanding = called - funded;
  const pct = called > 0 ? (funded / called) * 100 : 0;
  const open = data.filter((c) => c.status !== "FUNDED").length;

  return (
    <section className="kpis">
      <div className="kpi">
        <div className="kpi-label">Total called</div>
        <div className="kpi-value">{money(called)}</div>
        <div className="kpi-foot">{data.length} capital calls</div>
      </div>
      <div className="kpi">
        <div className="kpi-label">Funded</div>
        <div className="kpi-value kpi-positive">{money(funded)}</div>
        <div className="kpi-bar">
          <div style={{ width: `${Math.min(100, pct)}%` }} />
        </div>
        <div className="kpi-foot">{pct.toFixed(1)}% of total called</div>
      </div>
      <div className="kpi">
        <div className="kpi-label">Outstanding</div>
        <div className="kpi-value">{money(outstanding)}</div>
        <div className="kpi-foot">
          {open} call{open === 1 ? "" : "s"} awaiting funds
        </div>
      </div>
    </section>
  );
}
