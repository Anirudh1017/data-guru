import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

export interface ChartPoint {
  name: string
  value: number
}

interface Props {
  type: 'bar' | 'line'
  data: ChartPoint[]
  unit?: string
}

const PALETTE = ['#b7791f', '#8c5a12', '#c9a86a', '#111418', '#5f6368']

function shortDate(value: string) {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}

const money = (value: number) => `₹${Math.round(value).toLocaleString('en-IN')}`

export default function ChartView({ type, data, unit = '₹/quintal' }: Props) {
  if (!data.length) return null

  if (type === 'line') {
    const values = data.map((d) => d.value)
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
              formatter={(v) => [money(Number(v)), unit]}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#b7791f"
              strokeWidth={2.2}
              dot={false}
              activeDot={{ r: 4, fill: '#111418', stroke: '#fff', strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
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
