from pathlib import Path

import pytest

from backend.pipeline.pipeline_validator import (
    PipelineConfig,
    validate_pipeline_config,
)


def test_valid_default_configuration(tmp_path):
    config = PipelineConfig(input_dir=tmp_path)

    result = validate_pipeline_config(config)

    assert isinstance(result, PipelineConfig)
    assert result.input_dir == tmp_path.resolve()
    assert result.start_sol is None
    assert result.end_sol is None
    assert result.window_size == 10
    assert result.required_products == (
        "ATS",
        "PS",
        "RDS",
        "RHS",
        "TIRS",
        "WS",
    )


def test_valid_mapping_configuration(tmp_path):
    config = {
        "input_dir": tmp_path,
        "start_sol": 100,
        "end_sol": 250,
        "window_size": 5,
        "required_products": ["ats", "ws", "ATS"],
    }

    result = validate_pipeline_config(config)

    assert result.start_sol == 100
    assert result.end_sol == 250
    assert result.window_size == 5
    assert result.required_products == ("ATS", "WS")


def test_input_directory_must_exist(tmp_path):
    missing = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        validate_pipeline_config({
            "input_dir": missing,
        })


def test_input_path_must_be_directory(tmp_path):
    input_file = tmp_path / "input.csv"
    input_file.write_text("data", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        validate_pipeline_config({
            "input_dir": input_file,
        })


def test_input_directory_must_not_be_empty():
    with pytest.raises(ValueError):
        validate_pipeline_config({
            "input_dir": "",
        })


def test_input_directory_must_have_valid_type():
    with pytest.raises(TypeError):
        validate_pipeline_config({
            "input_dir": 123,
        })


def test_input_directory_is_required():
    with pytest.raises(ValueError):
        validate_pipeline_config({})


def test_unknown_configuration_key_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown"):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "unknown_option": True,
        })


@pytest.mark.parametrize(
    ("start_sol", "end_sol"),
    [
        (-1, 10),
        (10, -1),
        (20, 10),
    ],
)
def test_invalid_sol_range_is_rejected(
    tmp_path,
    start_sol,
    end_sol,
):
    with pytest.raises(ValueError):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "start_sol": start_sol,
            "end_sol": end_sol,
        })


def test_boolean_sol_is_rejected(tmp_path):
    with pytest.raises(TypeError):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "start_sol": True,
            "end_sol": 10,
        })


def test_partial_sol_range_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "start_sol": 100,
        })


@pytest.mark.parametrize(
    "field",
    ["gap_factor", "tolerance"],
)
@pytest.mark.parametrize(
    "value",
    [0, -1, float("inf"), float("nan")],
)
def test_invalid_positive_parameters_are_rejected(
    tmp_path,
    field,
    value,
):
    with pytest.raises(ValueError):
        validate_pipeline_config({
            "input_dir": tmp_path,
            field: value,
        })


@pytest.mark.parametrize(
    "window_size",
    [0, -1],
)
def test_invalid_window_size_is_rejected(
    tmp_path,
    window_size,
):
    with pytest.raises(ValueError):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "window_size": window_size,
        })


def test_boolean_window_size_is_rejected(tmp_path):
    with pytest.raises(TypeError):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "window_size": True,
        })


@pytest.mark.parametrize(
    "fraction",
    [0, -0.1, 1.1, float("inf"), float("nan")],
)
def test_invalid_min_sol_fraction_is_rejected(
    tmp_path,
    fraction,
):
    with pytest.raises(ValueError):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "min_sol_fraction": fraction,
        })


@pytest.mark.parametrize(
    "min_metrics",
    [0, 5, -1],
)
def test_invalid_min_metrics_is_rejected(
    tmp_path,
    min_metrics,
):
    with pytest.raises(ValueError):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "min_metrics": min_metrics,
        })


def test_boolean_min_metrics_is_rejected(tmp_path):
    with pytest.raises(TypeError):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "min_metrics": True,
        })


def test_required_products_are_normalized(tmp_path):
    result = validate_pipeline_config({
        "input_dir": tmp_path,
        "required_products": [" ats ", "ws", "ATS"],
    })

    assert result.required_products == ("ATS", "WS")


@pytest.mark.parametrize(
    "products",
    [
        [],
        (),
        "",
    ],
)
def test_empty_required_products_are_rejected(
    tmp_path,
    products,
):
    with pytest.raises((ValueError, TypeError)):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "required_products": products,
        })


def test_invalid_required_product_type_is_rejected(tmp_path):
    with pytest.raises(TypeError):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "required_products": ["ATS", 123],
        })


@pytest.mark.parametrize(
    "field",
    [
        "weight_files",
        "weight_integrity",
        "weight_quality",
        "weight_sync",
        "integrity_timestamps",
        "integrity_values",
    ],
)
@pytest.mark.parametrize(
    "value",
    [-1, float("inf"), float("nan")],
)
def test_invalid_weights_are_rejected(
    tmp_path,
    field,
    value,
):
    with pytest.raises(ValueError):
        validate_pipeline_config({
            "input_dir": tmp_path,
            field: value,
        })


def test_all_ranking_weights_cannot_be_zero(tmp_path):
    with pytest.raises(ValueError, match="ranking weight"):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "weight_files": 0,
            "weight_integrity": 0,
            "weight_quality": 0,
            "weight_sync": 0,
        })


def test_all_integrity_weights_cannot_be_zero(tmp_path):
    with pytest.raises(ValueError, match="integrity"):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "integrity_timestamps": 0,
            "integrity_values": 0,
        })


def test_boolean_weight_is_rejected(tmp_path):
    with pytest.raises(TypeError):
        validate_pipeline_config({
            "input_dir": tmp_path,
            "weight_files": True,
        })


def test_config_must_be_supported_type():
    with pytest.raises(TypeError):
        validate_pipeline_config("invalid")