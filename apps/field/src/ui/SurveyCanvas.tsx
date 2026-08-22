import type { PointerEvent as ReactPointerEvent } from "react";

import type { Survey, SurveyPointId } from "../domain/types";
import type { Finding } from "../domain/validation";
import {
  CANVAS_HEIGHT_MM,
  CANVAS_WIDTH_MM,
  buildElementViews,
  buildPhotoAnchorViews,
  buildSegmentViews,
  legendChips,
  pointsCentroid,
  segmentLabelPosition,
  segmentLabelRotation,
  touchToMm,
  type MmPoint,
} from "./viewModel";

/**
 * Medidas do traço, em mm do mundo do croqui. São a transposição das espessuras da
 * prancha 3a (viewBox 358 × 470) para a janela de 24 m × 31,5 m: 2,5 px ≈ 170 mm.
 */
const STROKE_MM = 170;
const STROKE_MISSING_MM = 200;
const DASH_MM = "500 350";
const POINT_RADIUS_MM = 400;
const POINT_SELECTED_RADIUS_MM = 780;
const PHOTO_RADIUS_MM = 800;
const LABEL_FONT_MM = 870;
const LABEL_OFFSET_MM = 950;
/** Alvo de toque generoso (o dedo não acerta 400 mm num desenho de 24 m). */
const POINT_HIT_RADIUS_MM = 1_100;
const SEGMENT_HIT_STROKE_MM = 1_100;

export interface SurveyCanvasProps {
  survey: Survey;
  findings: readonly Finding[];
  /** Primeiro ponto escolhido ao ligar dois pontos — realçado. */
  selectedPointId: SurveyPointId | null;
  selectedSegmentId: string | null;
  /** Toque no fundo marca ponto (só no modo "marcar ponto"). */
  onCanvasTap: ((point: MmPoint) => void) | null;
  onPointTap: ((pointId: SurveyPointId) => void) | null;
  onSegmentTap: ((segmentId: string) => void) | null;
}

/**
 * O desenho da coleta (prancha 3a). Renderiza o `Survey` e os `Finding` do motor —
 * nunca guarda geometria própria: o SVG é apresentação e captura de toque, e a fonte é
 * sempre `src/domain` (regra de `apps/field/AGENTS.md`).
 */
export function SurveyCanvas({
  survey,
  findings,
  selectedPointId,
  selectedSegmentId,
  onCanvasTap,
  onPointTap,
  onSegmentTap,
}: SurveyCanvasProps) {
  const segments = buildSegmentViews(survey, findings);
  const elements = buildElementViews(survey);
  const anchors = buildPhotoAnchorViews(survey);
  const centroid = pointsCentroid(survey);
  const chips = legendChips(survey, findings);

  const handleBackgroundTap = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (onCanvasTap === null) {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const mm = touchToMm(
      { x: event.clientX - rect.left, y: event.clientY - rect.top },
      { width: rect.width, height: rect.height },
    );
    if (mm !== null) {
      onCanvasTap(mm);
    }
  };

  return (
    <div className="canvas-wrap">
      <svg
        role="img"
        aria-label="Croqui do levantamento"
        viewBox={`0 0 ${CANVAS_WIDTH_MM} ${CANVAS_HEIGHT_MM}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={handleBackgroundTap}
      >
        {/* elementos: área suave com rótulo */}
        {elements.map((element) => (
          <g key={element.id}>
            <rect
              x={element.x_mm}
              y={element.y_mm}
              width={element.width_mm}
              height={element.height_mm}
              fill="var(--color-accent-soft)"
              stroke="var(--color-accent-line)"
              strokeWidth={STROKE_MM}
            />
            <text
              x={element.x_mm + element.width_mm / 2}
              y={element.y_mm + element.height_mm / 2}
              fontSize={LABEL_FONT_MM * 0.92}
              fontWeight={600}
              textAnchor="middle"
              dominantBaseline="middle"
              fill="var(--color-accent-text)"
            >
              {element.label}
            </text>
          </g>
        ))}

        {/* segmentos */}
        {segments.map((segment) => {
          const labelAt = segmentLabelPosition(segment, centroid, LABEL_OFFSET_MM);
          return (
            <g key={segment.id}>
              <line
                x1={segment.x1_mm}
                y1={segment.y1_mm}
                x2={segment.x2_mm}
                y2={segment.y2_mm}
                stroke="var(--color-ink)"
                strokeWidth={segment.id === selectedSegmentId ? STROKE_MM * 2 : STROKE_MM}
                strokeLinecap="round"
              />
              {segment.without_measurement && (
                <line
                  x1={segment.x1_mm}
                  y1={segment.y1_mm}
                  x2={segment.x2_mm}
                  y2={segment.y2_mm}
                  stroke="var(--color-state-error)"
                  strokeWidth={STROKE_MISSING_MM}
                  strokeDasharray={DASH_MM}
                />
              )}
              <text
                x={labelAt.x_mm}
                y={labelAt.y_mm}
                transform={`rotate(${segmentLabelRotation(segment)} ${labelAt.x_mm} ${labelAt.y_mm})`}
                fontSize={LABEL_FONT_MM}
                fontWeight={600}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={
                  segment.without_measurement
                    ? "var(--color-state-error)"
                    : "var(--color-accent-text)"
                }
              >
                {segment.label_text}
              </text>
            </g>
          );
        })}

        {/* pontos */}
        {survey.points.map((point) => (
          <g key={point.id}>
            {point.id === selectedPointId && (
              <circle
                cx={point.x_mm}
                cy={point.y_mm}
                r={POINT_SELECTED_RADIUS_MM}
                fill="none"
                stroke="var(--color-accent-text)"
                strokeWidth={STROKE_MM}
              />
            )}
            <circle
              cx={point.x_mm}
              cy={point.y_mm}
              r={POINT_RADIUS_MM}
              fill="var(--color-dark)"
            />
          </g>
        ))}

        {/* fotos ancoradas */}
        {anchors.map((anchor) => (
          <g key={anchor.id}>
            <circle
              cx={anchor.x_mm}
              cy={anchor.y_mm}
              r={PHOTO_RADIUS_MM}
              fill="var(--color-surface)"
              stroke="var(--color-ink-secondary)"
              strokeWidth={STROKE_MM * 0.6}
            />
            <text
              x={anchor.x_mm}
              y={anchor.y_mm}
              fontSize={LABEL_FONT_MM}
              textAnchor="middle"
              dominantBaseline="middle"
            >
              📷
            </text>
          </g>
        ))}

        {/* alvos de toque: depois do desenho, transparentes; ponto vence segmento */}
        {onSegmentTap !== null &&
          segments.map((segment) => (
            <line
              key={`hit-${segment.id}`}
              x1={segment.x1_mm}
              y1={segment.y1_mm}
              x2={segment.x2_mm}
              y2={segment.y2_mm}
              stroke="transparent"
              strokeWidth={SEGMENT_HIT_STROKE_MM}
              onPointerDown={(event) => {
                event.stopPropagation();
                onSegmentTap(segment.id);
              }}
            />
          ))}
        {onPointTap !== null &&
          survey.points.map((point) => (
            <circle
              key={`hit-${point.id}`}
              cx={point.x_mm}
              cy={point.y_mm}
              r={POINT_HIT_RADIUS_MM}
              fill="transparent"
              onPointerDown={(event) => {
                event.stopPropagation();
                onPointTap(point.id);
              }}
            />
          ))}
      </svg>
      <div className="canvas-legend">
        {chips.ok !== null && <span className="tag tag-ok">{chips.ok}</span>}
        {chips.error !== null && <span className="tag tag-error">{chips.error}</span>}
      </div>
    </div>
  );
}
