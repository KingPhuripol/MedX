export const meta = {
  name: 'product-loop',
  description: 'One slice through planner -> builder -> checker -> reviewers, looping on failure (max 3 build rounds)',
  whenToUse: 'Build one factory slice from docs/PROPOSAL.md with independent think/do/check/review roles',
  phases: [
    { title: 'Think', detail: 'planner writes slices/<id>/SPEC.md' },
    { title: 'Build', detail: 'builder implements on factory/<id>' },
    { title: 'Check', detail: 'independent checker runs tests + real system + metrics' },
    { title: 'Review', detail: 'safety + integration reviewers in parallel' },
  ],
}

const A = args
// Agents created after the session started are not registered yet: run them as
// general-purpose with their definition inlined (args.inline = {name: body}).
const role = (name) => (A.inline && A.inline[name])
  ? { agentType: 'general-purpose', pre: `You are acting as the "${name}" agent. Your definition:\n${A.inline[name]}\n\n` }
  : { agentType: name, pre: '' }
const WT = A.worktree
const CTX = `Work ONLY inside the git worktree at ${WT} (branch factory/${A.id}); cd there first and use absolute paths under it. Do not touch any other checkout. Source of truth: ${WT}/docs/PROPOSAL.md. Slice ${A.id}: ${A.title}. Gantt owner: ${A.owner}.`

const SPEC = { type: 'object', properties: {
  spec_path: { type: 'string' }, summary: { type: 'string' },
  acceptance: { type: 'array', items: { type: 'object', properties: {
    id: { type: 'string' }, criterion: { type: 'string' }, threshold: { type: 'string' }, how_measured: { type: 'string' } },
    required: ['id', 'criterion', 'threshold', 'how_measured'] } } },
  required: ['spec_path', 'summary', 'acceptance'] }
const BUILD = { type: 'object', properties: {
  status: { type: 'string', enum: ['DONE', 'BLOCKED'] }, commit: { type: 'string' }, summary: { type: 'string' },
  tests_run: { type: 'string' }, blockers: { type: 'array', items: { type: 'string' } } },
  required: ['status', 'commit', 'summary', 'tests_run'] }
const CHECK = { type: 'object', properties: {
  verdict: { type: 'string', enum: ['PASS', 'FAIL', 'SPEC_PROBLEM'] },
  metrics: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, value: { type: 'string' }, threshold: { type: 'string' }, pass: { type: 'boolean' } }, required: ['id', 'value', 'pass'] } },
  failures: { type: 'array', items: { type: 'string' } }, spec_problems: { type: 'array', items: { type: 'string' } },
  commands_run: { type: 'array', items: { type: 'string' } } },
  required: ['verdict', 'metrics', 'failures'] }
const REVIEW = { type: 'object', properties: {
  verdict: { type: 'string', enum: ['PASS', 'CONDITIONAL_PASS', 'FAIL', 'CRITICAL_FAIL'] },
  blockers: { type: 'array', items: { type: 'string' } }, conditions: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } },
  required: ['verdict', 'blockers', 'conditions', 'summary'] }

// An agent that ends without its structured result is retried once, continuing from its work.
const RETRY = '\n\nNOTE: a previous attempt ended without returning its structured result. Continue from the work already in the worktree (commit anything unfinished), then return the structured result.'
const tryAgent = async (prompt, opts) => {
  for (let i = 0; i < 2; i++) {
    try { const r = await agent(i ? prompt + RETRY : prompt, opts); if (r) return r }
    catch (e) { log(`${opts.label}: ${e.message}`) }
  }
  return null
}

phase('Think')
const think = (feedback) => tryAgent(`${role(A.planner).pre}${CTX}
ROLE: PLANNER (you plan; you do not implement). Goal of this slice:
${A.goal}
Proposal-derived acceptance to include (make each measurable, add more if the proposal requires): ${A.acceptance}
${feedback ? 'The checker reported the previous spec was ambiguous or unmeasurable; fix it:\n' + feedback : ''}
Write ${WT}/slices/${A.id}/SPEC.md (short: scope, out of scope, acceptance table with id/criterion/threshold/how measured, required test cases, clinical risks, run commands). Commit it on the branch. Return the acceptance list.`,
  { label: `plan:${A.planner}`, phase: 'Think', agentType: role(A.planner).agentType, schema: SPEC })

let spec = await think('')
if (!spec) return { error: 'planner failed' }
log(`SPEC: ${spec.acceptance.length} acceptance criteria`)

let findings = '', build = null, checks = [], reviews = [], rounds = 0, done = false
while (rounds < 3 && !done) {
  rounds++
  build = await tryAgent(`${role(A.builder).pre}${CTX}
ROLE: BUILDER. Implement exactly ${WT}/slices/${A.id}/SPEC.md with your own unit tests. Keep it minimal and runnable. Commit on the branch when tests pass.
${findings ? 'Fix these findings from the independent checker/reviewers first:\n' + findings : ''}`,
    { label: `build:${A.builder}#${rounds}`, phase: 'Build', agentType: role(A.builder).agentType, schema: BUILD })
  if (!build || build.status === 'BLOCKED') { log('builder blocked'); break }

  checks = (await parallel(A.checkers.map(c => () => tryAgent(`${role(c).pre}${CTX}
ROLE: CHECKER (independent; you did not build this; never edit product code). Check commit ${build.commit} against ${WT}/slices/${A.id}/SPEC.md: run the full test suite, start the real system and exercise it as the spec's users would, measure every acceptance criterion. Write ${WT}/artifacts/factory/${A.id}/check-${c}.json. Report SPEC_PROBLEM if a criterion is not measurable.`,
    { label: `check:${c}#${rounds}`, phase: 'Check', agentType: role(c).agentType, schema: CHECK })))).filter(Boolean)

  const specProblems = checks.filter(c => c.verdict === 'SPEC_PROBLEM').flatMap(c => c.spec_problems || [])
  if (specProblems.length) { spec = await think(specProblems.join('\n')) || spec; findings = ''; continue }
  const failed = checks.filter(c => c.verdict === 'FAIL')
  if (failed.length || !checks.length) { findings = failed.flatMap(c => c.failures).join('\n') || 'checker produced no result'; continue }

  reviews = (await parallel(A.reviewers.map(r => () => tryAgent(`${role(r).pre}${CTX}
ROLE: REVIEWER (read-only judgement; never create, edit or delete files). Review commit ${build.commit} of slice ${A.id} against ${WT}/slices/${A.id}/SPEC.md and the proposal: clinical safety, claim boundary, proposal fit, code quality. Checker results: ${JSON.stringify(checks.map(c => c.metrics))}. List only real blockers.`,
    { label: `review:${r}#${rounds}`, phase: 'Review', agentType: role(r).agentType, schema: REVIEW })))).filter(Boolean)
  const blockers = reviews.filter(r => r.verdict === 'FAIL' || r.verdict === 'CRITICAL_FAIL').flatMap(r => r.blockers)
  if (reviews.length < A.reviewers.length) { log('a reviewer returned no verdict; slice not done'); findings = ''; break }
  if (blockers.length) { findings = blockers.join('\n'); continue }
  done = true
}
return { slice: A.id, done, rounds, spec, build, checks, reviews, open_findings: done ? '' : findings }