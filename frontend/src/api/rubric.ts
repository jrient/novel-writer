/**
 * 剧本评审 Pipeline API 客户端
 */
import { request } from './request'

export interface DimensionScores {
  premise_innovation?: number
  opening_hook?: number
  character_depth?: number
  pacing_conflict?: number
  writing_dialogue?: number
  payoff_satisfaction?: number
  benchmark_differentiation?: number
  [k: string]: number | undefined
}

export interface ScoreDocxResponse {
  title: string
  detected_title: string
  predicted_score: number
  predicted_status: string
  dimension_scores: DimensionScores
  comments: string[]
  red_flags_hit: string[]
  green_flags_hit: string[]
  handbook_version: string
  model: string
  docx_token: string
  text_length: number
}

export const rubricApi = {
  /** 单本即时评分：贴入飞书 docx 链接，返回评分 + 红绿旗 + 建议 */
  scoreDocx(url: string, forceRefresh: boolean = true): Promise<ScoreDocxResponse> {
    return request.post('/rubric-pipeline/score-docx', {
      url,
      force_refresh: forceRefresh,
    })
  },
}
