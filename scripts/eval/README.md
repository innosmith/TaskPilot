# LLM-Eval-Suite (lokale Triage-Modelle)

Reproduzierbarer Benchmark, um bei neuen lokalen Modellen daten- statt
bauchbasiert zu entscheiden, welches die E-Mail-Triage am besten beherrscht.

## Warum

Die E-Mail-Triage laeuft auf einem lokalen Ollama-Modell (`triage_model`, Default
`qwen3.6:latest`). Der Tag `:latest` ist gleitend, und ca. monatlich erscheinen
neue Modelle. Diese Suite misst die fuer den Anwendungsfall entscheidenden
Dimensionen gegen ein Golden-Set aus echten, vom Berater bestaetigten Faellen.

## Gemessene Metriken

| Metrik | Bedeutung |
|--------|-----------|
| `contract_rate` | Anteil mit verwertbarem Pflicht-JSON-Block (Kernursache des frueheren ~11%-Stilldrops) |
| `class_accuracy` | Trefferquote `triage_class` vs. Ground Truth (`email_triage.status='acted'`) |
| `swiss_viol_per_mail` | Verstoesse gegen Schweizer Rechtschreibung (ß, ae/oe/ue) im Output |
| `avg_draft_similarity` | Aehnlichkeit des generierten Entwurfs zur real versendeten Antwort |
| `draft_swiss_viol_per_mail` | Schweizer-Verstoesse im Draft |
| `avg_latency_s` | Mittlere Antwortzeit pro Mail |

## Ablauf

```bash
# 1) Golden-Set aus der Prod-DB ziehen (bleibt lokal, ist gitignored)
python scripts/eval/export_golden_set.py \
    --container taskpilot-postgres-prod --limit 300

# 2) Kandidaten-Modelle vergleichen (muessen in `ollama list` vorhanden sein)
python scripts/eval/run_llm_eval.py \
    --models "qwen3.6:latest,gemma4:31b,deepseek-r1:70b,gpt-oss:20b" \
    --limit 80

# Ergebnis: scripts/eval/results/scoreboard_<ts>.md + .csv
```

Empfohlene Kandidaten (Stand der lokalen Maschine, Thinking-faehig priorisieren):
`qwen3.6:latest` (Baseline), `deepseek-r1:70b` (Reasoning), `gemma4:31b`
(DE-Qualitaet), `gpt-oss:20b`, ggf. `apertus:70b` (Schweizer Modell).

## Gewinner uebernehmen

Das beste Modell als FIXEN Tag in `.env` setzen (reproduzierbar, kein `:latest`):

```
TP_TRIAGE_MODEL=ollama/<modell>:<fixer-tag>
```

## Datenschutz

`scripts/eval/golden_set.jsonl` und `scripts/eval/results/` enthalten echte
E-Mail-Inhalte und sind via `.gitignore` ausgeschlossen. Nicht committen, nicht an
Cloud-Dienste schicken. Der Benchmark laeuft ausschliesslich lokal gegen Ollama.
