"""Interface de linha de comando para desenvolvimento e demonstrações locais."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID


def main() -> int:
    parser = argparse.ArgumentParser(prog="croquito-demo")
    subcommands = parser.add_subparsers(dest="command", required=True)
    synthetic = subcommands.add_parser("synthetic", help="gera o pacote sintético auditado")
    synthetic.add_argument("--output", type=Path, required=True)
    ingest = subcommands.add_parser("ingest", help="renderiza e registra um PDF local")
    ingest.add_argument("--input", type=Path, required=True)
    ingest.add_argument("--dataset-id", required=True)
    ingest.add_argument("--role", required=True)
    ingest.add_argument("--output", type=Path, default=Path("output/pdf"))
    ingest.add_argument("--dpi", type=int, default=200)
    propose_dataset_command = subcommands.add_parser(
        "propose-dataset",
        help="gera propostas geométricas não exportáveis para um dataset ingerido",
    )
    propose_dataset_command.add_argument("--manifest", type=Path, required=True)
    vision_eval_command = subcommands.add_parser(
        "vision-eval",
        help="executa a eval sintética determinística de visão",
    )
    vision_eval_command.add_argument("--output", type=Path, required=True)
    ocr_eval_command = subcommands.add_parser(
        "ocr-eval",
        help="executa a eval sintética determinística de corroboração de OCR",
    )
    ocr_eval_command.add_argument("--output", type=Path, required=True)
    review_artifacts_command = subcommands.add_parser(
        "review-artifacts",
        help="valida um review packet e gera overlay ligado à imagem",
    )
    review_artifacts_command.add_argument("--packet", type=Path, required=True)
    review_artifacts_command.add_argument("--image", type=Path, required=True)
    review_artifacts_command.add_argument("--output", type=Path, required=True)
    apply_review_command = subcommands.add_parser(
        "apply-review",
        help="aplica decisões humanas a um review packet e gera nova versão visual",
    )
    apply_review_command.add_argument("--packet", type=Path, required=True)
    apply_review_command.add_argument("--decisions", type=Path, required=True)
    apply_review_command.add_argument("--image", type=Path, required=True)
    apply_review_command.add_argument("--output", type=Path, required=True)
    associate_command = subcommands.add_parser(
        "associate-review",
        help="ranqueia propostas CV próximas das cotas sem confirmar associação",
    )
    associate_command.add_argument("--packet", type=Path, required=True)
    associate_command.add_argument("--proposals", type=Path, required=True)
    associate_command.add_argument("--output", type=Path, required=True)
    solve_rectangle_command = subcommands.add_parser(
        "solve-rectangle",
        help="soluciona um retângulo somente com leituras humanamente confirmadas",
    )
    solve_rectangle_command.add_argument("--packet", type=Path, required=True)
    solve_rectangle_command.add_argument("--request", type=Path, required=True)
    solve_rectangle_command.add_argument(
        "--associations",
        type=Path,
        required=True,
        help="JSON object mapping confirmed reading IDs to explicitly selected proposal IDs",
    )
    solve_rectangle_command.add_argument("--output", type=Path, required=True)
    rectangle_export_command = subcommands.add_parser(
        "rectangle-export",
        help="aprova e exporta uma solução retangular com decisão profissional explícita",
    )
    rectangle_export_command.add_argument("--solve-result", type=Path, required=True)
    rectangle_export_command.add_argument("--approval", type=Path, required=True)
    rectangle_export_command.add_argument("--output", type=Path, required=True)
    solve_trace_command = subcommands.add_parser(
        "solve-trace",
        help="resolve o traçado aceito em lote com as cotas confirmadas mandando",
    )
    solve_trace_command.add_argument("--packet", type=Path, required=True)
    solve_trace_command.add_argument(
        "--proposals",
        type=Path,
        required=True,
        help="VisionProposalSet ou lista JSON de propostas (extração)",
    )
    solve_trace_command.add_argument(
        "--associations",
        type=Path,
        required=True,
        help=(
            "JSON object mapping confirmed reading IDs to a proposal ID (vão do elemento) "
            "ou a uma lista de dois proposal IDs (vão entre dois elementos)"
        ),
    )
    solve_trace_command.add_argument(
        "--notes",
        type=Path,
        default=None,
        help=(
            "JSON object mapping confirmed annotation reading IDs to proposal IDs "
            '(nota presa) ou ao alvo "carimbo" (nota geral acima do título)'
        ),
    )
    solve_trace_command.add_argument(
        "--derived-dimensions",
        type=Path,
        default=None,
        help="JSON list de {proposal_id, near_x_px, near_y_px}: cota derivada de trecho desenhado",
    )
    solve_trace_command.add_argument(
        "--dimension-texts",
        type=Path,
        default=None,
        help='JSON object reading_id → texto exibido na cota do vão (ex.: "1,0 x 2,05")',
    )
    solve_trace_command.add_argument(
        "--acceptance",
        type=Path,
        required=True,
        help="TraceAcceptance JSON: aceite em lote identificado das propostas do traçado",
    )
    solve_trace_command.add_argument(
        "--required-criteria",
        action="append",
        default=[],
        metavar="CODIGO[=TEXTO]",
        help=(
            "critério de escopo do caso ainda não coberto: vira issue crítica na cena "
            "traçada e só sai por declaração explícita na aprovação"
        ),
    )
    solve_trace_command.add_argument("--output", type=Path, required=True)
    solve_trace_command.add_argument("--feature-id", default="tracado")
    solve_trace_command.add_argument("--title", default=None)
    solve_trace_command.add_argument(
        "--image-width",
        type=int,
        default=None,
        help="obrigatório quando --proposals é lista sem metadados de imagem",
    )
    solve_trace_command.add_argument("--image-height", type=int, default=None)
    trace_export_command = subcommands.add_parser(
        "trace-export",
        help="aprova e exporta um traçado resolvido com decisão profissional explícita",
    )
    trace_export_command.add_argument("--solve-result", type=Path, required=True)
    trace_export_command.add_argument("--approval", type=Path, required=True)
    trace_export_command.add_argument("--output", type=Path, required=True)
    solver_eval_command = subcommands.add_parser(
        "solver-eval",
        help="executa a eval sintética de revisão, solver, aprovação e DXF",
    )
    solver_eval_command.add_argument("--output", type=Path, required=True)
    extraction_eval_command = subcommands.add_parser(
        "extraction-eval",
        help="compara extração de geometria entre providers contra a tinta da página",
    )
    extraction_eval_command.add_argument("--image", type=Path, required=True)
    extraction_eval_command.add_argument("--manifest", type=Path, required=True)
    extraction_eval_command.add_argument("--output", type=Path, required=True)
    extraction_eval_command.add_argument(
        "--arm",
        action="append",
        default=[],
        metavar="NOME=PROVIDER:MODELO",
        help="eixo a comparar, ex.: opus=bedrock:anthropic.claude-opus-5",
    )
    extraction_eval_command.add_argument(
        "--step-gabarito",
        type=Path,
        default=None,
        help="gabarito do gate de fidelidade do degrau (StepGabarito); opcional",
    )
    degrau_fixture_command = subcommands.add_parser(
        "degrau-fixture",
        help="gera a fixture do muro em recuo (degrau) e o gabarito do gate de fidelidade",
    )
    degrau_fixture_command.add_argument("--output", type=Path, required=True)
    register_extraction_command = subcommands.add_parser(
        "register-extraction",
        help="assenta as propostas de uma eval de extração sobre a tinta e remede",
    )
    register_extraction_command.add_argument("--image", type=Path, required=True)
    register_extraction_command.add_argument("--output", type=Path, required=True)
    transcribe_readings_command = subcommands.add_parser(
        "transcribe-readings",
        help="transcreve cotas de uma página com um único eixo de provider",
    )
    transcribe_readings_command.add_argument("--image", type=Path, required=True)
    transcribe_readings_command.add_argument("--manifest", type=Path, required=True)
    transcribe_readings_command.add_argument("--output", type=Path, required=True)
    transcribe_readings_command.add_argument(
        "--arm",
        action="append",
        default=[],
        metavar="NOME=PROVIDER:MODELO",
        help="eixo único a transcrever, ex.: sonnet=bedrock:anthropic.claude-sonnet-5",
    )
    readings_to_packet_command = subcommands.add_parser(
        "readings-to-packet",
        help="converte leituras transcritas em DimensionReading e mescla num review packet",
    )
    readings_to_packet_command.add_argument("--readings", type=Path, required=True)
    readings_to_packet_command.add_argument("--base-packet", type=Path, required=True)
    readings_to_packet_command.add_argument("--manifest", type=Path, required=True)
    readings_to_packet_command.add_argument("--image", type=Path, required=True)
    readings_to_packet_command.add_argument("--output", type=Path, required=True)
    provider_contract_demo = subcommands.add_parser(
        "provider-contract-demo",
        help="executa adapters offline sobre uma imagem sintética não exportável",
    )
    provider_contract_demo.add_argument("--output", type=Path, required=True)
    local_worker_command = subcommands.add_parser(
        "local-worker-once",
        help="consome uma mensagem SQS local e avança o job para revisão",
    )
    local_worker_command.add_argument(
        "--fixtures",
        action="store_true",
        help=(
            "injeta a suíte sintética de providers; nenhuma chamada externa é feita e "
            "nenhum byte sai da máquina"
        ),
    )
    seed_review_command = subcommands.add_parser(
        "seed-review",
        help="liga um pacote de revisão autorizado a um job existente, sem decidir nada",
    )
    seed_review_command.add_argument("--job-id", required=True)
    seed_review_command.add_argument("--tenant-id", required=True)
    seed_review_command.add_argument("--packet", type=Path, required=True)
    seed_review_command.add_argument("--associations", type=Path, required=True)
    seed_review_command.add_argument("--proposals", type=Path, required=True)
    seed_review_command.add_argument("--rectangle-request", type=Path, required=True)
    seed_review_command.add_argument("--manifest", type=Path, required=True)
    seed_review_command.add_argument("--image", type=Path, required=True)
    seed_review_command.add_argument(
        "--required-criteria",
        action="append",
        default=[],
        metavar="CODIGO[=TEXTO]",
        help=(
            "critério do caso ainda não coberto pela cena métrica: só o código "
            "(ACC_GUA_001) ou código e texto (ACC_GUA_001=Perímetro e áreas limpos)"
        ),
    )
    seed_review_command.add_argument(
        "--operator-id",
        required=True,
        help="identificador lógico do responsável pela carga; nunca um segredo",
    )
    refresh_proposals_command = subcommands.add_parser(
        "refresh-proposals",
        help=(
            "recomputa o snapshot de propostas de um job vivo (mesmos ids vp_…) sem "
            "tocar decisões humanas"
        ),
    )
    refresh_proposals_command.add_argument("--job-id", required=True)
    refresh_proposals_command.add_argument("--tenant-id", required=True)
    refresh_proposals_command.add_argument("--proposals", type=Path, required=True)
    refresh_proposals_command.add_argument("--image", type=Path, required=True)
    refresh_proposals_command.add_argument(
        "--operator-id",
        required=True,
        help="identificador lógico do responsável pelo refresh; nunca um segredo",
    )
    args = parser.parse_args()

    if args.command == "seed-review":
        from croquito_worker.criteria import ScopeCriterionError, parse_criterion_declaration
        from croquito_worker.local_queue import LocalWorkerSettings
        from croquito_worker.review_seed import SeedInputs, SeedRefusedError, seed_review

        try:
            seed_criteria = tuple(
                parse_criterion_declaration(declaration) for declaration in args.required_criteria
            )
        except ScopeCriterionError as criterion_error:
            print(json.dumps({"refused": criterion_error.code}, ensure_ascii=False))
            return 2
        try:
            seed_result = seed_review(
                SeedInputs(
                    job_id=UUID(args.job_id),
                    tenant_id=args.tenant_id,
                    packet_path=args.packet,
                    associations_path=args.associations,
                    proposals_path=args.proposals,
                    rectangle_request_path=args.rectangle_request,
                    manifest_path=args.manifest,
                    image_path=args.image,
                    required_criteria=seed_criteria,
                    operator_id=args.operator_id,
                ),
                LocalWorkerSettings.from_environment(require_queue=False),
            )
        except SeedRefusedError as error:
            print(json.dumps({"refused": error.code}, ensure_ascii=False))
            return 2
        print(
            json.dumps(
                {
                    "job_id": str(seed_result.job_id),
                    "review_id": str(seed_result.review_id),
                    "review_version": seed_result.review_version,
                    "readings": seed_result.readings,
                    "proposals": seed_result.proposals,
                    "blockers": list(seed_result.blockers),
                    "required_criteria": [
                        criterion.model_dump(mode="json")
                        for criterion in seed_result.required_criteria
                    ],
                    "image_sha256": seed_result.image_sha256,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "refresh-proposals":
        from croquito_worker.local_queue import LocalWorkerSettings
        from croquito_worker.review_refresh import (
            RefreshInputs,
            RefreshRefusedError,
            refresh_proposals,
        )

        try:
            refresh_result = refresh_proposals(
                RefreshInputs(
                    job_id=UUID(args.job_id),
                    tenant_id=args.tenant_id,
                    proposals_path=args.proposals,
                    image_path=args.image,
                    operator_id=args.operator_id,
                ),
                LocalWorkerSettings.from_environment(require_queue=False),
            )
        except RefreshRefusedError as error:
            print(json.dumps({"refused": error.code}, ensure_ascii=False))
            return 2
        print(
            json.dumps(
                {
                    "job_id": str(refresh_result.job_id),
                    "review_id": str(refresh_result.review_id),
                    "review_version": {
                        "before": refresh_result.review_version_before,
                        "after": refresh_result.review_version_after,
                    },
                    "proposals": refresh_result.proposals,
                    "deltas": [
                        {
                            "proposal_id": delta.proposal_id,
                            "quality_score_before": delta.quality_score_before,
                            "quality_score_after": delta.quality_score_after,
                        }
                        for delta in refresh_result.deltas
                    ],
                    "calibration": refresh_result.calibration_status,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "local-worker-once":
        from croquito_worker.local_queue import run_local_worker_once
        from croquito_worker.providers import build_synthetic_provider_suite

        # A injeção é declarada pelo comando, nunca por variável de ambiente: ninguém
        # deve descobrir por acidente que respondeu com fixture.
        suite = build_synthetic_provider_suite() if args.fixtures else None
        processed = run_local_worker_once(provider_suite=suite)
        print(json.dumps({"processed": processed, "fixtures": bool(args.fixtures)}))
        return 0

    if args.command == "synthetic":
        from croquito_worker.pipeline import run_synthetic_pipeline

        synthetic_result = run_synthetic_pipeline(args.output)
        print(
            json.dumps(
                {
                    "status": synthetic_result.audit.status,
                    "dxf": str(synthetic_result.dxf_path),
                    "preview": str(synthetic_result.preview_path),
                    "package": str(synthetic_result.package_path),
                    "sha256": synthetic_result.audit.dxf_sha256,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "ingest":
        from croquito_worker.ingest import ingest_pdf

        manifest, manifest_path = ingest_pdf(
            args.input,
            args.output,
            dataset_id=args.dataset_id,
            role=args.role,
            dpi=args.dpi,
        )
        print(
            json.dumps(
                {
                    "dataset_id": manifest.dataset_id,
                    "pages": manifest.page_count,
                    "sha256": manifest.source_sha256,
                    "manifest": str(manifest_path),
                    "blank_candidates": [
                        page.number for page in manifest.pages if page.blank_candidate
                    ],
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "propose-dataset":
        from croquito_worker.vision_dataset import propose_dataset

        summary, summary_path = propose_dataset(args.manifest)
        print(
            json.dumps(
                {
                    "dataset_id": summary.dataset_id,
                    "pages": summary.page_count,
                    "proposals": summary.proposal_count,
                    "counts_by_kind": summary.counts_by_kind,
                    "safety_status": summary.safety_status,
                    "summary": str(summary_path),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "extraction-eval":
        from croquito_worker.extraction_eval import (
            ExtractionCandidate,
            StepGabarito,
            run_extraction_eval,
        )
        from croquito_worker.providers import build_extraction_arm

        if not args.arm:
            raise SystemExit("informe ao menos um --arm NOME=PROVIDER:MODELO")
        candidates = []
        for specification in args.arm:
            name, _, target = specification.partition("=")
            provider, _, model_id = target.partition(":")
            candidates.append(
                ExtractionCandidate(
                    name=name,
                    adapter=build_extraction_arm(provider=provider, model_id=model_id),
                )
            )
        step_gabarito = (
            StepGabarito.model_validate_json(args.step_gabarito.read_text())
            if args.step_gabarito is not None
            else None
        )
        extraction_report, extraction_report_path = run_extraction_eval(
            args.image,
            candidates,
            args.output,
            manifest_path=args.manifest,
            step_gabarito=step_gabarito,
        )
        print(
            json.dumps(
                {
                    "passed": extraction_report.passed,
                    "arms": [
                        {
                            "name": arm.name,
                            "model_id": arm.model_id,
                            "elements": arm.element_count,
                            "ink_coverage_mean": arm.ink_coverage_mean,
                            "corroborated_rate": arm.corroborated_rate,
                            "closed_regions": arm.closed_region_count,
                            "labelled_rate": arm.labelled_rate,
                            "latency_ms": arm.latency_ms,
                            "estimated_cost_usd": arm.estimated_cost_usd,
                            "step_preserved": (arm.step.step_preserved if arm.step else None),
                        }
                        for arm in extraction_report.arms
                    ],
                    "report": str(extraction_report_path),
                },
                ensure_ascii=False,
            )
        )
        return 0 if extraction_report.passed else 1
    if args.command == "degrau-fixture":
        import hashlib

        from croquito_worker.extraction_eval import build_degrau_step_gabarito
        from croquito_worker.io_utils import atomic_write_text
        from croquito_worker.synthetic import render_degrau_boundary_input

        output_dir = args.output
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = output_dir / "degrau.png"
        render_degrau_boundary_input(image_path)
        image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
        manifest_path = output_dir / "manifest.json"
        atomic_write_text(
            manifest_path,
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "dataset_id": "degrau-fixture",
                    "note": (
                        "fixture sintética auto-referente do gate de fidelidade do degrau; "
                        "sem conteúdo de cliente"
                    ),
                    "source_sha256": image_sha256,
                    "pages": [{"number": 1, "image_sha256": image_sha256}],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        gabarito_path = output_dir / "step-gabarito.json"
        atomic_write_text(
            gabarito_path,
            json.dumps(
                build_degrau_step_gabarito().model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        print(
            json.dumps(
                {
                    "image": str(image_path),
                    "manifest": str(manifest_path),
                    "step_gabarito": str(gabarito_path),
                    "image_sha256": image_sha256,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "register-extraction":
        from croquito_worker.extraction_eval import register_extraction_arms

        registered_report, registered_report_path = register_extraction_arms(
            args.output, args.image
        )
        print(
            json.dumps(
                {
                    "passed": registered_report.passed,
                    "arms": [
                        {
                            "name": arm.name,
                            "model_id": arm.model_id,
                            "elements": arm.element_count,
                            "ink_coverage_mean": arm.ink_coverage_mean,
                            "corroborated_rate": arm.corroborated_rate,
                            "notes": arm.notes,
                        }
                        for arm in registered_report.arms
                    ],
                    "report": str(registered_report_path),
                },
                ensure_ascii=False,
            )
        )
        return 0 if registered_report.passed else 1
    if args.command == "transcribe-readings":
        from croquito_worker.extraction_eval import ExtractionCandidate
        from croquito_worker.providers import build_extraction_arm
        from croquito_worker.transcription import run_transcription

        if len(args.arm) != 1:
            parser.error("informe exatamente um --arm NOME=PROVIDER:MODELO")
        specification = args.arm[0]
        name, _, target = specification.partition("=")
        provider, _, model_id = target.partition(":")
        candidate = ExtractionCandidate(
            name=name,
            adapter=build_extraction_arm(provider=provider, model_id=model_id),
        )
        artifact, transcription_report, readings_path, transcription_report_path = (
            run_transcription(args.image, candidate, args.output, manifest_path=args.manifest)
        )
        print(
            json.dumps(
                {
                    "arm": transcription_report.arm,
                    "provider": transcription_report.provider,
                    "model_id": transcription_report.model_id,
                    "readings": transcription_report.reading_count,
                    "counts_by_kind": transcription_report.counts_by_kind,
                    "counts_by_legibility": transcription_report.counts_by_legibility,
                    "estimated_cost_usd": transcription_report.estimated_cost_usd,
                    "readings_path": str(readings_path),
                    "report": str(transcription_report_path),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "readings-to-packet":
        from croquito_worker.review import load_review_packet
        from croquito_worker.transcription import (
            TranscriptionArtifact,
            merge_readings_into_packet,
            write_merge_artifacts,
        )

        artifact = TranscriptionArtifact.model_validate_json(
            args.readings.read_text(encoding="utf-8")
        )
        base_packet = load_review_packet(args.base_packet)
        merged_packet, merge_report = merge_readings_into_packet(
            artifact,
            base_packet,
            manifest_path=args.manifest,
            image_path=args.image,
        )
        packet_path, merge_report_path = write_merge_artifacts(
            merged_packet, merge_report, args.output
        )
        print(
            json.dumps(
                {
                    "base_readings": merge_report.base_reading_count,
                    "accepted": merge_report.accepted_count,
                    "duplicates": merge_report.duplicate_count,
                    "discarded": merge_report.discarded_count,
                    "total_readings": merge_report.total_reading_count,
                    "packet": str(packet_path),
                    "report": str(merge_report_path),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "vision-eval":
        from croquito_worker.vision_eval import run_synthetic_vision_eval

        vision_report, vision_report_path = run_synthetic_vision_eval(args.output)
        print(
            json.dumps(
                {
                    "passed": vision_report.passed,
                    "line_recall": vision_report.line_recall,
                    "circle_recall": vision_report.circle_recall,
                    "circle_candidate_precision": vision_report.circle_candidate_precision,
                    "unresolved_rate": vision_report.unresolved_rate,
                    "non_exportable_rate": vision_report.non_exportable_rate,
                    "proposals": vision_report.proposal_count,
                    "report": str(vision_report_path),
                },
                ensure_ascii=False,
            )
        )
        return 0 if vision_report.passed else 1
    if args.command == "ocr-eval":
        from croquito_worker.ocr_eval import run_ocr_corroboration_eval

        ocr_report, ocr_report_path = run_ocr_corroboration_eval(args.output)
        print(
            json.dumps(
                {
                    "passed": ocr_report.passed,
                    "reading_count": ocr_report.reading_count,
                    "confirmed_count": ocr_report.confirmed_count,
                    "confirmation_recall": ocr_report.confirmation_recall,
                    "false_confirmed_count": ocr_report.false_confirmed_count,
                    "report": str(ocr_report_path),
                },
                ensure_ascii=False,
            )
        )
        return 0 if ocr_report.passed else 1
    if args.command == "review-artifacts":
        from croquito_worker.review import load_review_packet, write_review_artifacts

        packet = load_review_packet(args.packet)
        packet_path, overlay_path = write_review_artifacts(packet, args.image, args.output)
        print(
            json.dumps(
                {
                    "status": packet.safety_status,
                    "readings": len(packet.readings),
                    "packet": str(packet_path),
                    "overlay": str(overlay_path),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "apply-review":
        from croquito_worker.review import (
            ReadingDecisionBatch,
            apply_reading_decisions,
            load_review_packet,
            write_review_artifacts,
        )

        packet = load_review_packet(args.packet)
        batch = ReadingDecisionBatch.model_validate_json(args.decisions.read_text(encoding="utf-8"))
        reviewed_packet = apply_reading_decisions(packet, batch)
        packet_path, overlay_path = write_review_artifacts(
            reviewed_packet,
            args.image,
            args.output,
        )
        confirmed_count = sum(
            1 for reading in reviewed_packet.readings if reading.status.value == "confirmed"
        )
        print(
            json.dumps(
                {
                    "status": reviewed_packet.safety_status,
                    "confirmed_readings": confirmed_count,
                    "packet": str(packet_path),
                    "overlay": str(overlay_path),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "associate-review":
        from croquito_worker.association import (
            associate_readings,
            load_proposal_set,
            write_association_set,
        )
        from croquito_worker.review import load_review_packet

        packet = load_review_packet(args.packet)
        proposals = load_proposal_set(args.proposals)
        associations = associate_readings(packet, proposals)
        association_path = write_association_set(associations, args.output)
        print(
            json.dumps(
                {
                    "candidates": len(associations.candidates),
                    "unassociated_readings": associations.unassociated_reading_ids,
                    "associations": str(association_path),
                    "safety_status": "observational_only",
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "solve-rectangle":
        from croquito_worker.rectangle_solver import (
            RectangleSolveRequest,
            solve_rectangle,
            write_solve_result,
        )
        from croquito_worker.review import load_review_packet

        packet = load_review_packet(args.packet)
        request = RectangleSolveRequest.model_validate_json(
            args.request.read_text(encoding="utf-8")
        )
        association_data = json.loads(args.associations.read_text(encoding="utf-8"))
        if not isinstance(association_data, dict) or not all(
            isinstance(reading_id, str) and isinstance(proposal_id, str)
            for reading_id, proposal_id in association_data.items()
        ):
            parser.error("--associations deve ser um objeto JSON de reading_id para proposal_id")
        rectangle_result = solve_rectangle(
            packet,
            request,
            confirmed_associations=association_data,
        )
        result_path = write_solve_result(rectangle_result, args.output)
        print(
            json.dumps(
                {
                    "status": rectangle_result.status,
                    "blockers": rectangle_result.blockers,
                    "scene_created": rectangle_result.scene is not None,
                    "result": str(result_path),
                },
                ensure_ascii=False,
            )
        )
        return 0 if rectangle_result.status == "solved_unapproved" else 2
    if args.command == "rectangle-export":
        from croquito_worker.dxf import export_scene_package
        from croquito_worker.rectangle_solver import (
            RectangleSolveResult,
            approve_rectangle,
            write_approved_revision,
        )
        from croquito_worker.review import SceneApproval

        parsed_result = RectangleSolveResult.model_validate_json(
            args.solve_result.read_text(encoding="utf-8")
        )
        approval = SceneApproval.model_validate_json(args.approval.read_text(encoding="utf-8"))
        approved = approve_rectangle(parsed_result, approval)
        _, approval_path = write_approved_revision(approved, args.output)
        export = export_scene_package(
            approved.scene,
            args.output,
            package_stem="retangulo-aprovado",
            extra_package_files=[approval_path],
        )
        print(
            json.dumps(
                {
                    "status": export.audit.status,
                    "revision": str(approved.scene.id),
                    "dxf": str(export.dxf_path),
                    "package": str(export.package_path),
                    "sha256": export.audit.dxf_sha256,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "solve-trace":
        from pydantic import TypeAdapter

        from croquito_worker.criteria import ScopeCriterionError, parse_criterion_declaration
        from croquito_worker.review import load_review_packet
        from croquito_worker.tracing import (
            DerivedDimensionRequest,
            TraceAcceptance,
            solve_trace,
            write_trace_result,
        )
        from croquito_worker.vision import VisionProposal, VisionProposalSet

        packet = load_review_packet(args.packet)
        proposals_text = args.proposals.read_text(encoding="utf-8")
        raw_proposals = json.loads(proposals_text)
        if isinstance(raw_proposals, dict):
            proposal_set = VisionProposalSet.model_validate(raw_proposals)
            if proposal_set.image_sha256 != packet.image_sha256:
                parser.error("digest das propostas diverge do review packet")
            trace_proposals = list(proposal_set.proposals)
            image_width = proposal_set.image_width_px
            image_height = proposal_set.image_height_px
        else:
            if args.image_width is None or args.image_height is None:
                parser.error(
                    "--image-width e --image-height são obrigatórios para lista de propostas"
                )
            trace_proposals = TypeAdapter(list[VisionProposal]).validate_python(raw_proposals)
            image_width = args.image_width
            image_height = args.image_height
        association_data = json.loads(args.associations.read_text(encoding="utf-8"))

        def _valid_target(target: object) -> bool:
            if isinstance(target, str):
                return True
            if isinstance(target, dict):
                # Vão declarado dentro de um elemento: validação estrutural fica no
                # solve_trace, que sabe transformar âncoras em faixas ou bloquear.
                return isinstance(target.get("proposal_id"), str) and isinstance(
                    target.get("spans_px"), list
                )
            return (
                isinstance(target, list)
                and len(target) == 2
                and all(isinstance(item, str) for item in target)
            )

        if not isinstance(association_data, dict) or not all(
            isinstance(reading_id, str) and _valid_target(target)
            for reading_id, target in association_data.items()
        ):
            parser.error(
                "--associations deve mapear reading_id para proposal_id, para uma lista "
                "de dois proposal_ids ou para {proposal_id, spans_px}"
            )
        note_data: dict[str, str] = {}
        if args.notes is not None:
            raw_notes = json.loads(args.notes.read_text(encoding="utf-8"))
            if not isinstance(raw_notes, dict) or not all(
                isinstance(reading_id, str) and isinstance(proposal_id, str)
                for reading_id, proposal_id in raw_notes.items()
            ):
                parser.error("--notes deve ser um objeto JSON de reading_id para proposal_id")
            note_data = raw_notes
        derived_requests: list[DerivedDimensionRequest] = []
        if args.derived_dimensions is not None:
            derived_requests = TypeAdapter(list[DerivedDimensionRequest]).validate_json(
                args.derived_dimensions.read_text(encoding="utf-8")
            )
        dimension_text_data: dict[str, str] = {}
        if args.dimension_texts is not None:
            raw_dimension_texts = json.loads(args.dimension_texts.read_text(encoding="utf-8"))
            if not isinstance(raw_dimension_texts, dict) or not all(
                isinstance(reading_id, str) and isinstance(text, str)
                for reading_id, text in raw_dimension_texts.items()
            ):
                parser.error("--dimension-texts deve ser um objeto JSON de reading_id para texto")
            dimension_text_data = raw_dimension_texts
        acceptance = TraceAcceptance.model_validate_json(
            args.acceptance.read_text(encoding="utf-8")
        )
        try:
            trace_criteria = [
                parse_criterion_declaration(declaration) for declaration in args.required_criteria
            ]
        except ScopeCriterionError as criterion_error:
            parser.error(f"--required-criteria inválido: {criterion_error.code}")
        trace_result = solve_trace(
            packet,
            trace_proposals,
            acceptance,
            confirmed_associations=association_data,
            note_associations=note_data,
            derived_dimension_requests=derived_requests,
            dimension_texts=dimension_text_data,
            required_criteria=trace_criteria,
            image_width=image_width,
            image_height=image_height,
            feature_id=args.feature_id,
            title=args.title,
        )
        trace_result_path = write_trace_result(trace_result, args.output)
        print(
            json.dumps(
                {
                    "status": trace_result.status,
                    "blockers": trace_result.blockers,
                    "unapplied_readings": trace_result.unapplied_reading_ids,
                    "exact_entities": trace_result.exact_entity_count,
                    "approximate_entities": trace_result.approximate_entity_count,
                    "notes": trace_result.note_count,
                    "scale_m_per_px": trace_result.scale_m_per_px,
                    "scene_created": trace_result.scene is not None,
                    "result": str(trace_result_path),
                },
                ensure_ascii=False,
            )
        )
        return 0 if trace_result.status == "solved_unapproved" else 2
    if args.command == "trace-export":
        from croquito_worker.dxf import export_scene_package
        from croquito_worker.review import SceneApproval
        from croquito_worker.tracing import (
            TraceSolveResult,
            approve_trace,
            write_approved_trace_revision,
        )

        trace_solve_result = TraceSolveResult.model_validate_json(
            args.solve_result.read_text(encoding="utf-8")
        )
        trace_approval = SceneApproval.model_validate_json(
            args.approval.read_text(encoding="utf-8")
        )
        approved_trace = approve_trace(trace_solve_result, trace_approval)
        _, trace_approval_path = write_approved_trace_revision(approved_trace, args.output)
        trace_export = export_scene_package(
            approved_trace.scene,
            args.output,
            package_stem="tracado-aprovado",
            extra_package_files=[trace_approval_path],
        )
        print(
            json.dumps(
                {
                    "status": trace_export.audit.status,
                    "revision": str(approved_trace.scene.id),
                    "dxf": str(trace_export.dxf_path),
                    "package": str(trace_export.package_path),
                    "sha256": trace_export.audit.dxf_sha256,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "solver-eval":
        from croquito_worker.solver_eval import run_solver_eval

        solver_report, solver_report_path = run_solver_eval(args.output)
        print(
            json.dumps(
                {
                    "passed": solver_report.passed,
                    "checks": solver_report.checks,
                    "audit_status": solver_report.audit_status,
                    "report": str(solver_report_path),
                },
                ensure_ascii=False,
            )
        )
        return 0 if solver_report.passed else 1
    if args.command == "provider-contract-demo":
        from croquito_worker.association import write_association_set
        from croquito_worker.provider_review import build_provider_review_snapshot
        from croquito_worker.providers import build_synthetic_provider_suite
        from croquito_worker.review import write_review_artifacts
        from croquito_worker.synthetic import render_synthetic_input

        image_path = args.output / "entrada-sintetica.png"
        render_synthetic_input(image_path)
        snapshot = build_provider_review_snapshot(
            image_path,
            dataset_id="synthetic-provider-contract-v1",
            suite=build_synthetic_provider_suite(),
        )
        packet_path, overlay_path = write_review_artifacts(snapshot.packet, image_path, args.output)
        association_path = write_association_set(snapshot.associations, args.output)
        print(
            json.dumps(
                {
                    "status": snapshot.packet.safety_status,
                    "readings": len(snapshot.packet.readings),
                    "packet": str(packet_path),
                    "overlay": str(overlay_path),
                    "associations": str(association_path),
                    "export": False,
                },
                ensure_ascii=False,
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
