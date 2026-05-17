"""Phase 11.2a tests: Pydantic v2 smoke baseline."""

import unittest

import pydantic
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ContractsPydanticTests(unittest.TestCase):
    def test_pydantic_major_is_v2(self):
        """Pydantic v2 보장 (계약 모델 base)."""
        self.assertEqual(int(pydantic.VERSION.split(".")[0]), 2)

    def test_pydantic_minor_at_least_13(self):
        """Pydantic >= 2.13 보장 (requirements.txt 따름)."""
        major, minor = pydantic.VERSION.split(".")[:2]
        self.assertEqual(int(major), 2)
        self.assertGreaterEqual(int(minor), 13)

    def test_basemodel_smoke(self):
        """BaseModel 정의 + 인스턴스 생성 정상 작동."""
        class SampleModel(BaseModel):
            name: str
            value: int

        sample = SampleModel(name="test", value=42)
        self.assertEqual(sample.name, "test")
        self.assertEqual(sample.value, 42)

    def test_model_validate_pattern(self):
        """model_validate() 패턴 입증 (shadow validation base)."""
        class SampleModel(BaseModel):
            name: str
            score: float = Field(ge=0, le=100)

        valid = SampleModel.model_validate({"name": "NVDA", "score": 82.5})
        self.assertEqual(valid.name, "NVDA")
        self.assertEqual(valid.score, 82.5)

        with self.assertRaises(ValidationError):
            SampleModel.model_validate({"name": "NVDA", "score": 150.0})

    def test_model_json_schema_pattern(self):
        """model_json_schema() 패턴 입증 (스키마 export base)."""
        class SampleModel(BaseModel):
            model_config = ConfigDict(extra="forbid")
            name: str
            value: int

        schema = SampleModel.model_json_schema()
        self.assertIn("properties", schema)
        self.assertIn("name", schema["properties"])
        self.assertIn("value", schema["properties"])

    def test_extra_forbid_pattern(self):
        """extra='forbid' 진짜 작동 입증 (계약 엄격성 base)."""
        class StrictModel(BaseModel):
            model_config = ConfigDict(extra="forbid")
            name: str

        with self.assertRaises(ValidationError):
            StrictModel.model_validate({"name": "test", "unknown_field": "X"})


if __name__ == "__main__":
    unittest.main()
