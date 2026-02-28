import { useState, useEffect, useMemo } from 'react'
import './App.css'

// ── API Configuration (will be updated with real URLs) ──
const API = {
  products: 'https://mock-products-eaa59f63.mangoriver-71e3a25a.swedencentral.azurecontainerapps.io/api/products',
  orders: 'https://mock-orders-2b601128.mangoriver-71e3a25a.swedencentral.azurecontainerapps.io/api/orders',
  customers: 'https://mock-customers-b51bed64.mangoriver-71e3a25a.swedencentral.azurecontainerapps.io/api/customers',
}

function useFetch(url) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    fetch(url).then(r => r.json()).then(d => { setData(d); setLoading(false) }).catch(() => setLoading(false))
  }, [url])
  return { data, loading }
}

// ── KPI Card ──
function KpiCard({ icon, color, value, label }) {
  return (
    <div className="kpi-card">
      <div className={`kpi-icon ${color}`}>{icon}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
    </div>
  )
}

// ── Bar Chart ──
function BarChart({ data, colorFn }) {
  const max = Math.max(...data.map(d => d.value), 1)
  return (
    <div className="chart-bar">
      {data.map((d, i) => (
        <div className="chart-bar-item" key={i}>
          <div className="chart-bar-value">{d.value}</div>
          <div className="chart-bar-fill" style={{ height: `${(d.value / max) * 170}px`, background: colorFn ? colorFn(i) : 'var(--primary)' }} />
          <div className="chart-bar-label">{d.label}</div>
        </div>
      ))}
    </div>
  )
}

// ── Donut Chart (CSS conic-gradient) ──
function DonutChart({ segments }) {
  const total = segments.reduce((s, x) => s + x.value, 0)
  let cum = 0
  const stops = segments.map(s => {
    const start = cum
    cum += (s.value / total) * 360
    return `${s.color} ${start}deg ${cum}deg`
  }).join(', ')

  return (
    <div className="donut-chart">
      <div className="donut-ring" style={{
        background: `conic-gradient(${stops})`,
        mask: 'radial-gradient(circle at center, transparent 45%, black 46%)',
        WebkitMask: 'radial-gradient(circle at center, transparent 45%, black 46%)',
      }} />
      <div className="donut-legend">
        {segments.map((s, i) => (
          <div className="legend-item" key={i}>
            <div className="legend-dot" style={{ background: s.color }} />
            <span>{s.label}: <strong>{s.value}</strong> ({total > 0 ? Math.round(s.value / total * 100) : 0}%)</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Overview Page ──
function Overview({ products, orders, customers }) {
  const totalRevenue = orders.reduce((s, o) => s + (o.total || 0), 0)
  const avgOrder = orders.length ? totalRevenue / orders.length : 0

  const statusCounts = orders.reduce((acc, o) => { acc[o.status] = (acc[o.status] || 0) + 1; return acc }, {})
  const statusSegments = [
    { label: 'Delivered', value: statusCounts.delivered || 0, color: '#1bc5bd' },
    { label: 'Shipped', value: statusCounts.shipped || 0, color: '#3699ff' },
    { label: 'Processing', value: statusCounts.processing || 0, color: '#ffa800' },
    { label: 'Pending', value: statusCounts.pending || 0, color: '#8950fc' },
    { label: 'Cancelled', value: statusCounts.cancelled || 0, color: '#f64e60' },
    { label: 'Refunded', value: statusCounts.refunded || 0, color: '#d63384' },
  ].filter(s => s.value > 0)

  const catCounts = products.reduce((acc, p) => { acc[p.category] = (acc[p.category] || 0) + 1; return acc }, {})
  const catData = Object.entries(catCounts).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: k, value: v }))
  const colors = ['#3699ff', '#1bc5bd', '#ffa800', '#8950fc', '#f64e60', '#d63384', '#20c997', '#6f42c1']

  const memberCounts = customers.reduce((acc, c) => { acc[c.membership] = (acc[c.membership] || 0) + 1; return acc }, {})
  const memberSegments = [
    { label: 'Platinum', value: memberCounts.Platinum || 0, color: '#8950fc' },
    { label: 'Gold', value: memberCounts.Gold || 0, color: '#ffa800' },
    { label: 'Silver', value: memberCounts.Silver || 0, color: '#b5b5c3' },
    { label: 'Bronze', value: memberCounts.Bronze || 0, color: '#cd7f32' },
  ].filter(s => s.value > 0)

  return (
    <>
      <div className="page-header">
        <h1>Dashboard Overview</h1>
        <p>Welcome back! Here's what's happening with your store.</p>
      </div>
      <div className="kpi-grid">
        <KpiCard icon="💰" color="blue" value={`$${totalRevenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} label="Total Revenue" />
        <KpiCard icon="📦" color="green" value={orders.length.toLocaleString()} label="Total Orders" />
        <KpiCard icon="🛍️" color="orange" value={products.length.toLocaleString()} label="Products" />
        <KpiCard icon="👥" color="purple" value={customers.length.toLocaleString()} label="Customers" />
      </div>
      <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
        <KpiCard icon="📊" color="blue" value={`$${avgOrder.toFixed(2)}`} label="Avg. Order Value" />
        <KpiCard icon="✅" color="green" value={statusCounts.delivered || 0} label="Delivered Orders" />
        <KpiCard icon="🚚" color="orange" value={statusCounts.shipped || 0} label="In Transit" />
        <KpiCard icon="⏳" color="purple" value={(statusCounts.pending || 0) + (statusCounts.processing || 0)} label="Pending/Processing" />
      </div>
      <div className="charts-grid">
        <div className="card">
          <div className="card-header"><h2>Products by Category</h2></div>
          <BarChart data={catData} colorFn={i => colors[i % colors.length]} />
        </div>
        <div className="card">
          <div className="card-header"><h2>Order Status</h2></div>
          <DonutChart segments={statusSegments} />
        </div>
      </div>
      <div className="charts-grid">
        <div className="card">
          <div className="card-header"><h2>Recent Orders</h2></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Order #</th><th>Customer</th><th>Total</th><th>Status</th><th>Date</th></tr></thead>
              <tbody>
                {orders.slice(0, 8).map((o, i) => (
                  <tr key={i}>
                    <td>{o.order_number}</td>
                    <td>{o.customer_email}</td>
                    <td>${o.total?.toFixed(2)}</td>
                    <td><span className={`badge badge-${o.status}`}>{o.status}</span></td>
                    <td>{o.order_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <div className="card-header"><h2>Customer Tiers</h2></div>
          <DonutChart segments={memberSegments} />
        </div>
      </div>
    </>
  )
}

// ── Products Page ──
function Products({ products, loading }) {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const categories = ['All', ...new Set(products.map(p => p.category))]
  const filtered = products.filter(p =>
    (category === 'All' || p.category === category) &&
    (p.name?.toLowerCase().includes(search.toLowerCase()) || p.brand?.toLowerCase().includes(search.toLowerCase()))
  )
  return (
    <>
      <div className="page-header"><h1>Products</h1><p>{products.length} items in catalog</p></div>
      <div className="card">
        <div className="toolbar">
          <input className="search-input" placeholder="Search products..." value={search} onChange={e => setSearch(e.target.value)} />
          <select className="filter-select" value={category} onChange={e => setCategory(e.target.value)}>
            {categories.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>
      </div>
      {loading ? <Loading /> : (
        <div className="product-grid">
          {filtered.map((p, i) => (
            <div className="product-card" key={i}>
              <img src={p.image_url || `https://picsum.photos/seed/${p.sku || i}/300/300`} alt={p.name} loading="lazy" />
              <div className="product-info">
                <div className="product-name" title={p.name}>{p.name}</div>
                <div className="product-category">{p.brand} · {p.category}</div>
                <div className="product-footer">
                  <span className="product-price">${p.price?.toFixed(2)}</span>
                  <span className="product-rating">⭐ {p.rating?.toFixed(1)}</span>
                </div>
                <div className="product-footer" style={{ marginTop: 6 }}>
                  <span className="product-stock">{p.stock} in stock</span>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{p.sku}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

// ── Orders Page ──
function Orders({ orders, loading }) {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('All')
  const [page, setPage] = useState(1)
  const perPage = 15
  const statuses = ['All', ...new Set(orders.map(o => o.status))]
  const filtered = orders.filter(o =>
    (status === 'All' || o.status === status) &&
    (o.order_number?.toLowerCase().includes(search.toLowerCase()) || o.customer_email?.toLowerCase().includes(search.toLowerCase()) || o.product_name?.toLowerCase().includes(search.toLowerCase()))
  )
  const totalPages = Math.ceil(filtered.length / perPage)
  const paged = filtered.slice((page - 1) * perPage, page * perPage)

  return (
    <>
      <div className="page-header"><h1>Orders</h1><p>{orders.length} total orders</p></div>
      <div className="card">
        <div className="toolbar">
          <input className="search-input" placeholder="Search orders..." value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} />
          <select className="filter-select" value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}>
            {statuses.map(s => <option key={s}>{s}</option>)}
          </select>
          <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{filtered.length} results</span>
        </div>
      </div>
      {loading ? <Loading /> : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Order #</th><th>Product</th><th>Customer</th><th>Qty</th><th>Total</th><th>Payment</th><th>Status</th><th>City</th><th>Date</th></tr></thead>
              <tbody>
                {paged.map((o, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600 }}>{o.order_number}</td>
                    <td>{o.product_name}</td>
                    <td>{o.customer_email}</td>
                    <td>{o.quantity}</td>
                    <td>${o.total?.toFixed(2)}</td>
                    <td style={{ textTransform: 'capitalize' }}>{o.payment_method?.replace('_', ' ')}</td>
                    <td><span className={`badge badge-${o.status}`}>{o.status}</span></td>
                    <td>{o.shipping_city}</td>
                    <td>{o.order_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div className="pagination">
              <button disabled={page === 1} onClick={() => setPage(p => p - 1)}>‹</button>
              {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                const p = page <= 4 ? i + 1 : page >= totalPages - 3 ? totalPages - 6 + i : page - 3 + i
                if (p < 1 || p > totalPages) return null
                return <button key={p} className={p === page ? 'active' : ''} onClick={() => setPage(p)}>{p}</button>
              })}
              <button disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>›</button>
            </div>
          )}
        </div>
      )}
    </>
  )
}

// ── Customers Page ──
function Customers({ customers, loading }) {
  const [search, setSearch] = useState('')
  const [tier, setTier] = useState('All')
  const tiers = ['All', 'Platinum', 'Gold', 'Silver', 'Bronze']
  const filtered = customers.filter(c =>
    (tier === 'All' || c.membership === tier) &&
    (`${c.first_name} ${c.last_name} ${c.email} ${c.city}`.toLowerCase().includes(search.toLowerCase()))
  )
  return (
    <>
      <div className="page-header"><h1>Customers</h1><p>{customers.length} registered customers</p></div>
      <div className="card">
        <div className="toolbar">
          <input className="search-input" placeholder="Search customers..." value={search} onChange={e => setSearch(e.target.value)} />
          <select className="filter-select" value={tier} onChange={e => setTier(e.target.value)}>
            {tiers.map(t => <option key={t}>{t}</option>)}
          </select>
        </div>
      </div>
      {loading ? <Loading /> : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Location</th><th>Membership</th><th>Orders</th><th>Total Spent</th><th>Joined</th></tr></thead>
              <tbody>
                {filtered.map((c, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600 }}>{c.first_name} {c.last_name}</td>
                    <td>{c.email}</td>
                    <td>{c.phone}</td>
                    <td>{c.city}, {c.state}</td>
                    <td><span className={`badge badge-${c.membership?.toLowerCase()}`}>{c.membership}</span></td>
                    <td>{c.orders_count}</td>
                    <td style={{ fontWeight: 600 }}>${c.total_spent?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                    <td>{c.joined_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}

function Loading() {
  return <div className="loading"><div className="spinner" />Loading data...</div>
}

// ── Main App ──
export default function App() {
  const [page, setPage] = useState('overview')
  const { data: products, loading: loadingP } = useFetch(API.products)
  const { data: orders, loading: loadingO } = useFetch(API.orders)
  const { data: customers, loading: loadingC } = useFetch(API.customers)

  const loading = loadingP || loadingO || loadingC

  const nav = [
    { id: 'overview', icon: '📊', label: 'Overview' },
    { id: 'products', icon: '🛍️', label: 'Products' },
    { id: 'orders', icon: '📦', label: 'Orders' },
    { id: 'customers', icon: '👥', label: 'Customers' },
  ]

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-brand"><span>🛒</span> ShopDash</div>
        <nav className="sidebar-nav">
          {nav.map(n => (
            <button key={n.id} className={`sidebar-link ${page === n.id ? 'active' : ''}`} onClick={() => setPage(n.id)}>
              <span className="icon">{n.icon}</span>{n.label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="main">
        {loading && page === 'overview' ? <Loading /> :
          page === 'overview' ? <Overview products={products} orders={orders} customers={customers} /> :
          page === 'products' ? <Products products={products} loading={loadingP} /> :
          page === 'orders' ? <Orders orders={orders} loading={loadingO} /> :
          <Customers customers={customers} loading={loadingC} />
        }
      </main>
    </div>
  )
}
