import { useId, useState } from 'react'
import type { EvidenceMap as EvidenceMapData, MapNode } from '../api'
import './evidence-map.css'

export function EvidenceMap({ map, onInspect }: {
  map: EvidenceMapData | null | undefined
  onInspect: (sourceId: string) => void
}) {
  const selectId = useId()
  const [fileId, setFileId] = useState('')
  const [selectedId, setSelectedId] = useState('')
  if (!map?.nodes.length) return null
  const files = map.nodes.filter(node => node.kind === 'file')
  const file = files.find(node => node.id === fileId) ?? files[0]
  if (!file) return null
  const nodes = map.nodes.filter(node => node.path === file.path && node.revision === file.revision)
  const selected = nodes.find(node => node.id === selectedId) ?? file
  const edges = map.edges.filter(edge => nodes.some(node => node.id === edge.child_id))
  const parentEdge = edges.find(edge => edge.child_id === selected.id)
  const unplaced = nodes.filter(node => node.kind !== 'file' && !edges.some(edge => edge.child_id === node.id))
  const sourceIds = new Set(file.sources.map(source => source.source_id))
  const issues = map.issues.filter(issue => sourceIds.has(issue.source_id))

  function renderNode(node: MapNode, depth = 0) {
    const children = edges.filter(edge => edge.parent_id === node.id)
      .map(edge => nodes.find(item => item.id === edge.child_id)!)
    return (
      <li key={node.id}>
        <button
          className="map-node"
          aria-label={`Inspect ${node.kind} ${node.label}`}
          aria-pressed={selected.id === node.id}
          onClick={() => setSelectedId(node.id)}
        >
          <span className="map-node-kind">{node.kind}</span>
          <code>{node.label}</code>
          <small>{node.kind === 'file' ? `Revision ${node.revision}` : `Lines ${node.start_line}–${node.end_line}`}</small>
        </button>
        {children.length > 0 && (
          <ul className={depth >= 3 ? 'map-tree map-tree-deep' : 'map-tree'}>
            {children.map(child => renderNode(child, depth + 1))}
          </ul>
        )}
      </li>
    )
  }

  return (
    <details className="evidence-map" open={map.edges.length > 0}>
      <summary>Evidence map <span>Structure in cited passages</span></summary>
      <div className="map-content" role="region" aria-label="Evidence map">
        <p>Each connection means <strong>contains</strong> in the indexed source.
          Select a block, then open a supporting passage.</p>
        <label className="map-file-label" htmlFor={selectId}>Map file</label>
        <select id={selectId} value={file.id} onChange={event => {
          setFileId(event.target.value)
          setSelectedId('')
        }}>
          {files.map(item => <option key={item.id} value={item.id}>{item.path} · {item.revision}</option>)}
        </select>
        <ul className="map-tree map-tree-root">{renderNode(file)}</ul>
        {unplaced.length > 0 && (
          <>
            <p className="map-gap">Containment unavailable for these definitions:</p>
            <ul className="map-tree map-tree-root">{unplaced.map(node => renderNode(node))}</ul>
          </>
        )}
        <section className="map-selection" aria-label="Selected map block">
          <strong>{selected.label}</strong>
          {parentEdge && <p>Contained by {nodes.find(node => node.id === parentEdge.parent_id)?.label}
            {' · '}{parentEdge.method} · {parentEdge.source_ids.join(', ')}</p>}
          <p>{selected.kind === 'file' ? 'Cited excerpts from this file:' : 'Definition coverage in each passage:'}</p>
          <div className="map-source-buttons">
            {selected.sources.map(source => (
              <button key={source.source_id} onClick={() => onInspect(source.source_id)}>
                Open {source.source_id}{source.coverage ? ` · ${source.coverage} span` : ''}
              </button>
            ))}
          </div>
        </section>
        {issues.length > 0 && <ul className="map-gaps" aria-label="Map coverage gaps">
          {issues.map((issue, index) => <li key={index}>
            {issue.source_id}: {issue.detail} <span>({issue.reason.replaceAll('_', ' ')})</span>
          </li>)}
        </ul>}
        {map.omitted_nodes > 0 && <p className="map-gap">
          {map.omitted_nodes} {map.omitted_nodes === 1 ? 'block' : 'blocks'} omitted by the saved map limit of {map.node_limit}.
          Change the limit in Evidence context for a new question.
        </p>}
        <p className="map-scope">Scope: this answer’s cited passages. Calls, runtime behavior,
          and connections to other services remain outside this view.</p>
      </div>
    </details>
  )
}
