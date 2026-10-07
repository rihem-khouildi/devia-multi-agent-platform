import unittest

from config.settings import Settings
from core.models import GeneratedCode
from core.quality_analyzer import QualityAnalyzer


class QualityAnalyzerDuplicationTest(unittest.TestCase):
    def setUp(self):
        self.analyzer = QualityAnalyzer(Settings().pipeline)

    def test_duplication_ignores_java_structural_boilerplate(self):
        code = GeneratedCode(
            files={
                "src/main/java/com/example/app/controller/ApplicationController.java": """package com.example.app.controller;

import com.example.app.dto.ApplicationRequest;
import com.example.app.dto.ApplicationResponse;
import com.example.app.service.ApplicationService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApplicationController {
    private final ApplicationService service;

    public ApplicationController(ApplicationService service) {
        this.service = service;
    }

    @GetMapping("/applications")
    public ResponseEntity<ApplicationResponse> findById() {
        return ResponseEntity.ok(service.findById(1L));
    }
}
""",
                "src/main/java/com/example/app/controller/CandidateController.java": """package com.example.app.controller;

import com.example.app.dto.CandidateRequest;
import com.example.app.dto.CandidateResponse;
import com.example.app.service.CandidateService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CandidateController {
    private final CandidateService service;

    public CandidateController(CandidateService service) {
        this.service = service;
    }

    @GetMapping("/candidates")
    public ResponseEntity<CandidateResponse> findById() {
        return ResponseEntity.ok(service.findById(1L));
    }
}
""",
            },
            pom_xml="<project></project>",
            readme="demo",
        )

        duplication = self.analyzer._compute_duplication_percent(code.all_source_files())

        self.assertEqual(duplication, 0.0)

    def test_duplication_still_detects_repeated_business_logic_blocks(self):
        duplicated_block = "\n".join(
            [
                '        String status = "OK";',
                '        String message = "hello";',
                "        if (status != null && message != null) {",
                "            audit(status, message);",
                "            return status + message;",
                "        }",
                '        return "fallback";',
            ]
        )
        code = GeneratedCode(
            files={
                "src/main/java/com/example/app/BadService.java": (
                    "package com.example.app;\n"
                    "public class BadService {\n"
                    "    public String alpha() {\n"
                    f"{duplicated_block}\n"
                    "    }\n"
                    "    public String beta() {\n"
                    f"{duplicated_block}\n"
                    "    }\n"
                    "    private void audit(String status, String message) {\n"
                    "        System.out.println(status + message);\n"
                    "    }\n"
                    "}\n"
                )
            },
            pom_xml="<project></project>",
            readme="demo",
        )

        duplication = self.analyzer._compute_duplication_percent(code.all_source_files())

        self.assertGreater(duplication, 30.0)

    def test_duplication_ignores_generated_crud_controllers_with_annotation_arguments(self):
        code = GeneratedCode(
            files={
                "src/main/java/com/example/app/controller/ApplicationController.java": """package com.example.app.controller;

import com.example.app.dto.ApplicationRequest;
import com.example.app.dto.ApplicationResponse;
import com.example.app.service.ApplicationService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/applications")
@RequiredArgsConstructor
public class ApplicationController {
    private final ApplicationService service;

    @GetMapping
    @Operation(summary = "List all")
    public ResponseEntity<List<ApplicationResponse>> findAll() {
        return ResponseEntity.ok(service.findAll());
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get by id")
    public ResponseEntity<ApplicationResponse> findById(@PathVariable Long id) {
        return ResponseEntity.ok(service.findById(id));
    }

    @PostMapping
    @Operation(summary = "Create")
    public ResponseEntity<ApplicationResponse> create(@Valid @RequestBody ApplicationRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.create(request));
    }

    @PutMapping("/{id}")
    @Operation(summary = "Update")
    public ResponseEntity<ApplicationResponse> update(@PathVariable Long id, @Valid @RequestBody ApplicationRequest request) {
        return ResponseEntity.ok(service.update(id, request));
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "Delete")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
""",
                "src/main/java/com/example/app/controller/CandidateController.java": """package com.example.app.controller;

import com.example.app.dto.CandidateRequest;
import com.example.app.dto.CandidateResponse;
import com.example.app.service.CandidateService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/candidates")
@RequiredArgsConstructor
public class CandidateController {
    private final CandidateService service;

    @GetMapping
    @Operation(summary = "List all")
    public ResponseEntity<List<CandidateResponse>> findAll() {
        return ResponseEntity.ok(service.findAll());
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get by id")
    public ResponseEntity<CandidateResponse> findById(@PathVariable Long id) {
        return ResponseEntity.ok(service.findById(id));
    }

    @PostMapping
    @Operation(summary = "Create")
    public ResponseEntity<CandidateResponse> create(@Valid @RequestBody CandidateRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.create(request));
    }

    @PutMapping("/{id}")
    @Operation(summary = "Update")
    public ResponseEntity<CandidateResponse> update(@PathVariable Long id, @Valid @RequestBody CandidateRequest request) {
        return ResponseEntity.ok(service.update(id, request));
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "Delete")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
""",
            },
            pom_xml="<project></project>",
            readme="demo",
        )

        duplication = self.analyzer._compute_duplication_percent(code.all_source_files())

        self.assertEqual(duplication, 0.0)


if __name__ == "__main__":
    unittest.main()
