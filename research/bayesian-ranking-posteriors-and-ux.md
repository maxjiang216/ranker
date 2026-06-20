For your setting (20–80 items, one user, one session, Bayesian BT model refit after every answer, O(N²) affordable), you can afford to optimize for UX and statistical reliability rather than asymptotic efficiency.

A useful way to think about the session is that there are three distinct states:

1. **The scores are still moving.**
2. **The scores are mostly fixed, but local ordering is uncertain.**
3. **Additional questions produce negligible changes.**

The stopping rule and progress estimate should be built around detecting state (3).

---

# 1. Stopping criteria

The literature on active ranking generally favors confidence-based stopping rather than fixed budgets, and adaptive procedures can achieve near-optimal sample complexity by stopping once confidence intervals separate items sufficiently. ([arXiv][1])

I would not use a single stopping criterion alone.

## Option A: Fixed comparison budget

### Pros

* Extremely predictable UX.
* Easy progress bar.
* No risk of pathological long sessions.

### Cons

* Wastes questions on easy rankings.
* Stops too early on difficult rankings.
* Doesn't adapt to user inconsistency.

### Practical values

For BT-style active querying with information gain:

* easy users/preferences: ~1.5–2N comparisons
* typical: ~2–4N
* difficult/noisy: ~4–6N

For N=40:

* 80 questions often feels surprisingly good
* 120–160 usually stabilizes rankings
* > 200 often gives diminishing returns

I would not hard-stop at kN. I'd use it as a soft cap.

---

## Option B: Posterior uncertainty threshold

Examples:

Stop when:

```
P(rank_i == modal_rank_i) > 0.95
for 90% of items
```

or

```
mean posterior SD(score_i) < ε
```

### Pros

* Principled Bayesian criterion.
* Adapts naturally to easy vs difficult rankings.

### Cons

* Score uncertainty does not necessarily equal rank uncertainty.
* Some adjacent items remain ambiguous forever.

This is much better if computed on ranks rather than scores.

I would compute posterior rank samples:

```
sample θ
sort θ
record ranks
```

Then estimate:

* posterior rank variance
* probability of each item's modal rank
* probability adjacent items are reversed

These directly correspond to user-visible uncertainty.

---

## Option C: Rank stability

Example:

```
ranking unchanged for last m=15 answers
```

### Pros

* Intuitive.
* Easy to explain.

### Cons

* Can be misleading.

You can get:

```
A B C D
```

oscillating with:

```
P(B>C)=0.51
```

and appear stable despite high uncertainty.

Or:

```
A B C D
A C B D
```

flip repeatedly despite negligible practical difference.

I would never use this alone.

---

## Option D: Marginal information gain threshold

This matches your pair-selection objective.

Stop when:

```
max_pair EIG(i,j) < τ
```

### Pros

* Measures expected value of one more question.
* Automatically accounts for score uncertainty.
* Automatically accounts for pair ambiguity.

### Cons

* Pure information metrics can keep asking tiny refinements forever.

---

# Recommendation

Use a hybrid:

Stop when:

### Primary criterion

```
max_pair_EIG < τ
```

for some threshold.

AND

### Secondary criterion

Either:

```
90% of adjacent pairs satisfy

P(i > j) > 0.9
or
P(i > j) < 0.1
```

or

```
90% of items have
P(rank = modal_rank) > 0.8
```

### Safety cap

```
max_questions = 5N
```

### Minimum floor

```
min_questions = N
```

before auto-stop is even considered.

This behaves very well in practice.

---

# Early stopping by the user

Always allow:

> Finish now

because Bayesian posteriors naturally support partial information.

At every point you can output:

* posterior mean ranking
* uncertainty bands
* unresolved regions

The ranking simply becomes coarser.

Think of ranking quality as graceful degradation rather than success/failure.

---

# 2. Live progress estimate

This is surprisingly difficult.

The user wants:

> How many questions remain?

You cannot know exactly.

I would estimate it probabilistically.

---

# Estimated remaining questions

Let

```
I_t = current best-pair EIG
```

and

```
I_stop = threshold
```

Fit an exponential decay online:

```
I_t ≈ I0 exp(-λ t)
```

Then predict:

```
remaining
≈ log(I_t / I_stop) / λ
```

Update λ after every answer.

It won't be perfect, but users mainly want an order-of-magnitude estimate.

---

# Which progress proxy is best?

## Posterior entropy

Pros:

* principled
* smooth

Cons:

* hard to explain
* score entropy isn't rank entropy

I would not expose this directly.

---

## Number of uncertain adjacent pairs

Define:

```
adjacent pair uncertain
if

0.25 < P(i > j) < 0.75
```

Then:

```
progress
=
1
-
uncertain_adjacent_pairs
/
(N-1)
```

This is excellent because adjacent swaps dominate perceived ranking quality.

---

## Kendall-τ stability

Measure:

```
τ(current ranking,
ranking 10 questions ago)
```

Pros:

* intuitive

Cons:

* lagging indicator
* can plateau too early

Useful as a secondary metric.

---

# Recommendation

Internally track:

1. max EIG
2. uncertain adjacent pairs
3. rolling Kendall-τ

Expose:

> Ranking confidence: 78%
>
> About 15–25 questions remaining.
>
> 6 neighboring items are still too close to call.

This maps directly onto what users care about.

---

# 3. Tier/group output

This is where uncertainty matters most.

Users strongly dislike:

```
Tier 1:
A

Tier 2:
B
```

when:

```
P(A>B)=0.54
```

---

# Gap-based splitting

Sort posterior means:

```
θ1 > θ2 > ...
```

Split on large score gaps.

### Pros

* simple
* deterministic

### Cons

* ignores uncertainty entirely
* unstable

Not recommended.

---

# k-means / Jenks

Treat posterior means as 1-D points.

### Pros

* visually appealing
* can reveal structure

### Cons

* still ignores posterior uncertainty
* can split statistically indistinguishable items

I would only use this as a visualization aid.

---

# Credible-overlap merging

Example:

```
95% CI(A)
overlaps
95% CI(B)
```

then place together.

### Pros

* respects uncertainty

### Cons

* interval overlap is conservative
* overlap/non-overlap is not equivalent to significance

Two items can have overlapping intervals while:

```
P(A>B)=0.98
```

Conversely, non-overlap can be overly strict.

---

# Better approach

Use posterior pair probabilities directly.

Build graph:

```
edge(i,j)
iff

0.2 < P(i > j) < 0.8
```

Interpretation:

> We cannot confidently order these items.

Connected components become tiers.

For stricter tiers:

```
0.1 < P(i > j) < 0.9
```

This approach:

* respects uncertainty
* avoids arbitrary score gaps
* naturally groups near-ties

Since N≤80, computing all O(N²) pair probabilities is trivial.

---

# Automatic number of tiers

I would derive tiers entirely from the probability graph.

No k selection required.

The number of tiers emerges from the posterior.

---

# Optional user control

Slider:

```
Conservative grouping
←────────→
Aggressive grouping
```

which adjusts threshold:

```
0.4–0.6
0.3–0.7
0.2–0.8
0.1–0.9
```

Very intuitive.

---

# 4. Confidence / uncertainty display

Most users do not understand:

* posterior SD
* credible intervals
* entropy

They understand:

1. confidence
2. ties
3. unresolved decisions

---

# Per-item uncertainty

Show:

```
1. A
2. B
3. C
```

with confidence badges:

```
A   Very certain
B   Fairly certain
C   Uncertain
```

Compute:

```
confidence_i
=
P(rank_i = modal_rank_i)
```

or

```
1 - normalized rank variance
```

---

# Show unsettled regions

This is the clearest visualization.

Example:

```
1 A
2 B
3 C
---------
4 D
5 E
6 F
---------
7 G
```

and highlight:

```
D ↔ E  54/46
E ↔ F  58/42
```

with text:

> These items are still essentially tied.

Adjacent ambiguity matters far more than absolute uncertainty.

---

# Pair confidence matrix

Since N is small:

Compute:

```
P(i > j)
```

for all pairs.

Display as heatmap internally or in advanced mode.

This immediately reveals:

* tiers
* uncertainty regions
* near ties

---

# Suggested UX

Main ranking:

```
1 A
2 B
3 C
4 D  (~ tied)
5 E  (~ tied)
6 F
```

Below:

> Remaining uncertainty:
>
> • D vs E: 52/48
>
> • E vs F: 60/40

This is usually sufficient.

---

# 5. Handling detected intransitivity

Cycles are expected in human preference data.

Combinatorial Hodge approaches explicitly separate transitive score structure from cyclic residual structure and provide a principled decomposition of inconsistency. ([arXiv][2])

For a single-user session:

**Do not treat cycles as errors.**

They're information.

---

# Detecting cycles

Compute Hodge decomposition:

```
comparisons
=
gradient component
+
curl component
+
harmonic component
```

Monitor:

```
inconsistency_ratio
=
||curl||²
/
||total||²
```

and local triangle residuals.

---

# What to do?

## Option 1: Re-ask

Good only for very large residuals.

Example:

```
A > B
B > C
C > A
```

with high confidence.

Ask:

> Earlier your choices implied a preference cycle involving A, B and C. Want to reconsider one of these comparisons?

Offer once.

Never repeatedly challenge the user.

---

## Option 2: Down-weight

Dangerous.

You don't know whether:

* user made a mistake
* preferences are genuinely context-dependent

Automatically down-weighting imposes a transitivity assumption.

I would avoid this.

---

## Option 3: Report only

This is my recommendation.

Example:

> Most of your preferences are internally consistent.
>
> A few groups of items seem genuinely hard to order and form preference loops.

Then highlight:

```
A
B
C
```

as:

> Circular preference cluster.

This feels validating rather than accusatory.

---

# Overall recommended design

### Ask pairs

Choose pair by expected information gain.

### Auto-stop

```
questions ≥ N
AND
max_EIG < τ
AND
90% of adjacent pairs have
P(order)>0.9
OR
questions ≥ 5N
```

### Progress

Display:

* estimated remaining questions
* uncertain adjacent pairs
* confidence percentage

### Final ranking

Produce:

1. ordered list
2. uncertainty badges
3. tiers from posterior pair probabilities
4. unresolved neighboring pairs

### Intransitivity

Compute Hodge residuals, surface them gently, optionally offer one reconsideration, and otherwise report them as meaningful ambiguity rather than mistakes.

For single-session ranking tools, this combination tends to feel remarkably "human": it stops when additional questions no longer meaningfully change the ordering, groups items that are effectively tied, and honestly communicates where the user's own preferences remain unresolved.

[1]: https://arxiv.org/abs/1606.08842?utm_source=chatgpt.com "Active Ranking from Pairwise Comparisons and when Parametric Assumptions Don't Help"
[2]: https://arxiv.org/abs/2601.07158?utm_source=chatgpt.com "The Bayesian Intransitive Bradley-Terry Model via Combinatorial Hodge Theory"

