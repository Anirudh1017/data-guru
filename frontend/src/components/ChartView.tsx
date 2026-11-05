import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

export interface ChartPoint {
  name: string
  value: number
  [key: string]: string | number
}

interface Props {
  type: 'bar' | 'line'
  data: ChartPoint[]
  unit?: string
}

const PALETTE = ['#b7791f', '#111418', '#1f9d55', '#8c5a12', '#5f6368', '#c9a86a']

function shortDate(value: string) {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}

const money = (value: number) => `₹${Math.round(value).toLocaleString('en-IN')}`

export default function ChartView({ type, data, unit = '₹/quintal' }: Props) {
  if (!data.length) return null

  const seriesKeys = Object.keys(data[0] || {}).filter(
    (k) => k !== 'name' && k !== 'value' && typeof data[0][k] === 'number'
  )
  const activeKeys = seriesKeys.length >= 2 ? seriesKeys : ['value']

  if (type === 'line') {
    const values = data.flatMap((d) =>
      activeKeys.map((k) => Number(d[k])).filter((v) => !Number.isNaN(v))
    )
    const min = Math.min(...values)
    const max = Math.max(...values)
    const pad = Math.max((max - min) * 0.18, max * 0.01, 1)
    return (
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, left: 4, right: 18, bottom: 4 }}>
            <CartesianGrid vertical={false} stroke="#efede8" />
            <XAxis
              dataKey="name"
              tickFormatter={shortDate}
              tick={{ fontSize: 11, fill: '#5f6368' }}
              tickLine={false}
              axisLine={{ stroke: '#e8e6e1' }}
              minTickGap={24}
            />
            <YAxis
              domain={[Math.floor(min - pad), Math.ceil(max + pad)]}
              tick={{ fontSize: 11, fill: '#5f6368' }}
              tickLine={false}
              axisLine={false}
              width={52}
              tickFormatter={(v) => Number(v).toLocaleString('en-IN')}
            />
            <Tooltip
              labelFormatter={(label) => shortDate(String(label))}
              formatter={(v, name) => [
                money(Number(v)),
                activeKeys.length > 1 ? String(name).replace(/\s*\(₹\/quintal\)/i, '') : unit,
              ]}
            />
            {activeKeys.length > 1 && (
              <Legend
                verticalAlign="top"
                height={28}
                formatter={(val) => String(val).replace(/\s*\(₹\/quintal\)/i, '')}
              />
            )}
            {activeKeys.map((key, idx) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={PALETTE[idx % PALETTE.length]}
                strokeWidth={2.2}
                dot={false}
                activeDot={{ r: 4, fill: PALETTE[idx % PALETTE.length], stroke: '#fff', strokeWidth: 2 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (activeKeys.length > 1) {
    return (
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, left: 4, right: 18, bottom: 4 }}>
            <CartesianGrid vertical={false} stroke="#efede8" />
            <XAxis
              dataKey="name"
              tickFormatter={shortDate}
              tick={{ fontSize: 11, fill: '#5f6368' }}
              tickLine={false}
              axisLine={{ stroke: '#e8e6e1' }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#5f6368' }}
              tickLine={false}
              axisLine={false}
              width={52}
              tickFormatter={(v) => Number(v).toLocaleString('en-IN')}
            />
            <Tooltip
              cursor={{ fill: '#fafaf8' }}
              formatter={(v, name) => [money(Number(v)), String(name).replace(/\s*\(₹\/quintal\)/i, '')]}
            />
            <Legend
              verticalAlign="top"
              height={28}
              formatter={(val) => String(val).replace(/\s*\(₹\/quintal\)/i, '')}
            />
            {activeKeys.map((key, idx) => (
              <Bar
                key={key}
                dataKey={key}
                fill={PALETTE[idx % PALETTE.length]}
                radius={[4, 4, 0, 0]}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, left: 8, right: 24, bottom: 4 }}>
          <CartesianGrid horizontal={false} stroke="#efede8" />
          <XAxis
            type="number"
            tick={{ fontSize: 11, fill: '#5f6368' }}
            tickLine={false}
            axisLine={{ stroke: '#e8e6e1' }}
            tickFormatter={(v) => Number(v).toLocaleString('en-IN')}
          />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fontSize: 12, fill: '#111418' }}
            tickLine={false}
            axisLine={false}
            width={140}
          />
          <Tooltip
            cursor={{ fill: '#fafaf8' }}
            formatter={(v) => [money(Number(v)), unit]}
          />
          <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={20} isAnimationActive={false}>
            {data.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
