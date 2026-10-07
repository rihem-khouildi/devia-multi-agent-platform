import logging
import asyncio
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock

from agents.tester import TesterAgent
from config.settings import Settings
from core.maven_compiler import MavenBuildRunner
from core.models import AnalysisResult, Endpoint, Entity, EntityField, GeneratedCode, StoryScope


class TesterSanitizationTests(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.tester = TesterAgent(Settings().hf)
        self.analysis = AnalysisResult(
            entities=[
                Entity(
                    name="Candidate",
                    fields=[
                        EntityField(name="id", type="Long"),
                        EntityField(name="name", type="String"),
                        EntityField(name="email", type="String"),
                        EntityField(name="address", type="String"),
                    ],
                )
            ],
            endpoints=[Endpoint(method="GET", path="/api/candidates", description="list candidates")],
            gherkin_scenarios=[],
            architecture_notes="notes",
            package_base="com.example.app",
            service_name="Candidate",
            dependencies=[],
            business_rules=[],
        )
        self.generated_code = GeneratedCode(
            files={
                "src/main/java/com/example/app/entity/Candidate.java": """package com.example.app.entity;

public class Candidate {
    private Long id;
    private String name;
    private String email;
    private String address;

    public Candidate() {}
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getAddress() { return address; }
    public void setAddress(String address) { this.address = address; }
}
""",
                "src/main/java/com/example/app/dto/CandidateRequest.java": """package com.example.app.dto;

public class CandidateRequest {
    private String name;
    private String email;
    private String address;

    public void setName(String name) { this.name = name; }
    public void setEmail(String email) { this.email = email; }
    public void setAddress(String address) { this.address = address; }
}
""",
                "src/main/java/com/example/app/dto/CandidateResponse.java": """package com.example.app.dto;

public class CandidateResponse {
    private String name;
    private String email;
    private String address;

    public String getName() { return name; }
    public String getEmail() { return email; }
    public String getAddress() { return address; }
}
""",
                "src/main/java/com/example/app/repository/CandidateRepository.java": """package com.example.app.repository;

public interface CandidateRepository {
    java.util.Optional<com.example.app.entity.Candidate> findById(Long id);
    java.util.List<com.example.app.entity.Candidate> findAll();
    com.example.app.entity.Candidate save(com.example.app.entity.Candidate candidate);
    boolean existsById(Long id);
    void deleteById(Long id);
}
""",
                "src/main/java/com/example/app/entity/Application.java": """package com.example.app.entity;

public class Application {
    private Long id;
    private String jobTitle;
    private String status;
    private Candidate candidate;

    public Application() {}
    public Application(Long id, String jobTitle, String status, Candidate candidate) {
        this.id = id;
        this.jobTitle = jobTitle;
        this.status = status;
        this.candidate = candidate;
    }
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getJobTitle() { return jobTitle; }
    public void setJobTitle(String jobTitle) { this.jobTitle = jobTitle; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Candidate getCandidate() { return candidate; }
    public void setCandidate(Candidate candidate) { this.candidate = candidate; }
}
""",
                "src/main/java/com/example/app/repository/ApplicationRepository.java": """package com.example.app.repository;

public interface ApplicationRepository {
    java.util.Optional<com.example.app.entity.Application> findById(Long id);
    java.util.List<com.example.app.entity.Application> findAll();
    com.example.app.entity.Application save(com.example.app.entity.Application application);
    void delete(com.example.app.entity.Application application);
}
""",
                "src/main/java/com/example/app/service/CandidateService.java": """package com.example.app.service;

import com.example.app.dto.CandidateRequest;
import com.example.app.dto.CandidateResponse;
import java.util.List;

public interface CandidateService {
    List<CandidateResponse> findAll();
    CandidateResponse findById(Long id);
    CandidateResponse create(CandidateRequest request);
    CandidateResponse update(Long id, CandidateRequest request);
    void delete(Long id);
}
""",
                "src/main/java/com/example/app/service/impl/CandidateServiceImpl.java": """package com.example.app.service.impl;

import com.example.app.dto.CandidateRequest;
import com.example.app.dto.CandidateResponse;
import com.example.app.entity.Candidate;
import com.example.app.repository.ApplicationRepository;
import com.example.app.repository.CandidateRepository;

public class CandidateServiceImpl {
    private CandidateRepository repository;
    private ApplicationRepository applicationRepository;
    public java.util.List<CandidateResponse> findAll() { return java.util.List.of(); }
    public CandidateResponse findById(Long id) { return null; }
    public CandidateResponse create(CandidateRequest request) { return null; }
    public CandidateResponse update(Long id, CandidateRequest request) { return null; }
    public void delete(Long id) {}
}
""",
            },
            pom_xml="<project></project>",
            readme="demo",
        )

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_sanitize_rewrites_known_project_types_and_adds_missing_imports(self):
        raw_tests = {
            "src/test/java/com/example/app/service/CandidateServiceTest.java": """package com.example.app.service;

import com.example.app.dto.CandidateRequest;
import com.example.app.dto.CandidateResponse;
import com.example.app.service.impl.CandidateServiceImpl;
import org.junit.jupiter.api.Test;
import org.mockito.InjectMocks;
import org.mockito.Mock;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

public class CandidateServiceTest {

    @Mock
    private CandidateRepository candidateRepository;

    @InjectMocks
    private CandidateServiceImpl candidateService;

    @Test
    void create_CasNominal() {
        when(candidateRepository.findById(any())).thenReturn(Optional.of(new CandidateEntity()));
        CandidateRequest request = new CandidateRequest();
        request.setName("John Doe");
        request.setEmail("john.doe@example.com");
        request.setAddress("123 Main St");
        List<CandidateResponse> responses = candidateService.findAll();
        assertThat(responses).isNotNull();
    }
}
""",
        }

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, self.analysis)
        content = sanitized["src/test/java/com/example/app/service/CandidateServiceTest.java"]

        self.assertNotIn("CandidateEntity", content)
        self.assertIn("new Candidate()", content)
        self.assertIn("import com.example.app.entity.Candidate;", content)
        self.assertIn("import com.example.app.repository.CandidateRepository;", content)

    def test_sanitize_drops_tests_with_unknown_service_calls(self):
        raw_tests = {
            "src/test/java/com/example/app/integration/CandidateIntegrationTest.java": """import com.example.app.service.CandidateService;
import com.example.app.model.Candidate;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;

public class CandidateIntegrationTest {
    @Mock
    private CandidateService candidateService;

    @Test
    void invalidScenario() {
        candidateService.createCandidate(new Candidate());
    }
}
""",
        }

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, self.analysis)

        self.assertIn("src/test/java/com/example/app/service/CandidateServiceTest.java", sanitized)
        self.assertIn("src/test/java/com/example/app/controller/CandidateControllerTest.java", sanitized)
        self.assertNotIn("src/test/java/com/example/app/integration/CandidateIntegrationTest.java", sanitized)

    def test_prompt_helpers_expose_allowed_classes_and_callable_methods(self):
        symbol_index = self.tester._build_project_symbol_index(self.generated_code)

        allowed_classes = self.tester._render_allowed_project_classes(symbol_index, "com.example.app")
        callable_methods = self.tester._render_callable_methods(symbol_index, "Service")

        self.assertIn("com.example.app.service.CandidateService", allowed_classes)
        self.assertIn("com.example.app.service.impl.CandidateServiceImpl", allowed_classes)
        self.assertIn("CandidateService: create, delete, findAll, findById, update", callable_methods)
        self.assertIn("CandidateServiceImpl: create, delete, findAll, findById, update", callable_methods)

    def test_context_block_renders_source_file_labels_and_signatures(self):
        files = {
            "src/main/java/com/example/app/service/CandidateService.java": self.generated_code.files[
                "src/main/java/com/example/app/service/CandidateService.java"
            ],
            "src/main/java/com/example/app/repository/CandidateRepository.java": self.generated_code.files[
                "src/main/java/com/example/app/repository/CandidateRepository.java"
            ],
        }

        block = self.tester._render_context_block(files, max_files=2, max_chars_per_file=500)

        self.assertIn("// === src/main/java/com/example/app/service/CandidateService.java ===", block)
        self.assertIn("CandidateResponse create(CandidateRequest request)", block)
        self.assertIn("// === src/main/java/com/example/app/repository/CandidateRepository.java ===", block)

    def test_sanitize_rewrites_main_java_test_paths_into_src_test_java(self):
        raw_tests = {
            "src/main/java/com/example/app/controller/CandidateControllerTest.java": """package com.example.app.controller;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class CandidateControllerTest {
    @Test
    void smokeTest() {
        assertThat(true).isTrue();
    }
}
""",
        }

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, self.analysis)

        self.assertIn("src/test/java/com/example/app/controller/CandidateControllerTest.java", sanitized)
        self.assertNotIn("src/main/java/com/example/app/controller/CandidateControllerTest.java", sanitized)

    def test_sanitize_removes_duplicate_field_declarations(self):
        raw_tests = {
            "src/test/java/com/example/app/service/CandidateServiceTest.java": """package com.example.app.service;

import com.example.app.repository.ApplicationRepository;
import com.example.app.repository.CandidateRepository;
import com.example.app.service.impl.CandidateServiceImpl;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.InjectMocks;
import org.mockito.Mock;

public class CandidateServiceTest {

    @Mock
    private CandidateRepository candidateRepository;

    @Mock
    private ApplicationRepository applicationRepository;

    @Mock
    private CandidateServiceImpl candidateService;

    @InjectMocks
    private CandidateService candidateService;

    @BeforeEach
    void setUp() {
        candidateService = new CandidateServiceImpl(candidateRepository, applicationRepository);
    }

    @Test
    void smokeTest() {}
}
""",
        }

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, self.analysis)
        content = sanitized["src/test/java/com/example/app/service/CandidateServiceTest.java"]

        self.assertEqual(content.count("candidateService;"), 1)
        self.assertEqual(content.count("@InjectMocks"), 1)
        self.assertEqual(content.count("@Mock"), 2)

    def test_sanitize_rewrites_void_mocks_missing_error_constant_and_entity_ctor(self):
        raw_tests = {
            "src/test/java/com/example/app/controller/CandidateControllerTest.java": """package com.example.app.controller;

import com.example.app.dto.CandidateResponse;
import com.example.app.entity.Candidate;
import com.example.app.exception.ErrorResponse;
import com.example.app.exception.ResourceNotFoundException;
import com.example.app.service.CandidateService;
import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.when;

class CandidateControllerTest {

    private CandidateService candidateService;

    @Test
    void sanitizeKnownBrokenPatterns() {
        when(candidateService.delete(1L)).thenThrow(ResourceNotFoundException.class);
        Candidate candidate = new Candidate("John Doe", "john.doe@example.com", "123 Main St");
        String expected = ErrorResponse.MESSAGE_GENERIC_ERROR;
    }
}
""",
        }

        self.generated_code.files["src/main/java/com/example/app/exception/GlobalExceptionHandler.java"] = """package com.example.app.exception;

import org.springframework.http.HttpStatus;

public class GlobalExceptionHandler {
    private ErrorResponse buildError(int status, String message) { return null; }
    public ErrorResponse handleGeneric(Exception ex) {
        return buildError(HttpStatus.INTERNAL_SERVER_ERROR.value(), "An unexpected error occurred");
    }
}
"""
        self.generated_code.files["src/main/java/com/example/app/exception/ErrorResponse.java"] = """package com.example.app.exception;

public class ErrorResponse {
    private String message;
    public String getMessage() { return message; }
}
"""
        self.generated_code.files["src/main/java/com/example/app/exception/ResourceNotFoundException.java"] = """package com.example.app.exception;

public class ResourceNotFoundException extends RuntimeException {
    public ResourceNotFoundException(String message) { super(message); }
}
"""

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, self.analysis)
        content = sanitized["src/test/java/com/example/app/controller/CandidateControllerTest.java"]

        self.assertIn("doThrow(ResourceNotFoundException.class).when(candidateService).delete(1L);", content)
        self.assertIn('String expected = "An unexpected error occurred";', content)
        self.assertIn('new Candidate(null, "John Doe", "john.doe@example.com", "123 Main St")', content)
        self.assertIn("import static org.mockito.Mockito.doThrow;", content)

    def test_sanitize_replaces_invalid_mockito_controller_test_with_smoke_test(self):
        raw_tests = {
            "src/test/java/com/example/app/controller/CandidateControllerTest.java": """package com.example.app.controller;

import com.example.app.dto.CandidateRequest;
import com.example.app.dto.CandidateResponse;
import com.example.app.exception.ResourceNotFoundException;
import com.example.app.service.CandidateService;
import org.junit.jupiter.api.Test;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.when;

class CandidateControllerTest {
    private CandidateService candidateService;

    @Test
    void brokenMockitoSyntaxFallsBackToSmokeTest() {
        doThrow(ResourceNotFoundException.class).when(candidateService).create(any(CandidateRequest.class))).thenReturn(new CandidateResponse());
        when(candidateService.findById(1L);
    }
}
""",
        }

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, self.analysis)
        content = sanitized["src/test/java/com/example/app/controller/CandidateControllerTest.java"]

        self.assertIn("class CandidateControllerTest", content)
        self.assertIn("void smokeTest_compiles()", content)
        self.assertNotIn("doThrow(ResourceNotFoundException.class)", content)
        self.assertNotIn("when(candidateService.findById(1L);", content)

    def test_sanitize_rewrites_repository_test_with_invalid_entity_members_to_smoke_test(self):
        raw_tests = {
            "src/test/java/com/example/app/repository/CandidateRepositoryTest.java": """package com.example.app.repository;

import com.example.app.entity.Candidate;
import org.junit.jupiter.api.Test;

class CandidateRepositoryTest {

    @Test
    void invalidEntityAssumptionsFallBackToSmokeTest() {
        Candidate candidate = new Candidate();
        candidate.getPhone();
    }
}
""",
        }

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, self.analysis)
        content = sanitized["src/test/java/com/example/app/repository/CandidateRepositoryTest.java"]

        self.assertIn("class CandidateRepositoryTest", content)
        self.assertIn("void smokeTest_compiles()", content)
        self.assertNotIn("getPhone()", content)

    def test_sanitize_rewrites_service_test_with_invalid_constructor_types_to_smoke_test(self):
        raw_tests = {
            "src/test/java/com/example/app/service/CandidateServiceTest.java": """package com.example.app.service;

import com.example.app.dto.CandidateRequest;
import org.junit.jupiter.api.Test;

class CandidateServiceTest {

    @Test
    void invalidConstructorTypesFallBackToSmokeTest() {
        Long id = 1L;
        CandidateRequest request = new CandidateRequest(id, "name", "email");
    }
}
""",
        }

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, self.analysis)
        content = sanitized["src/test/java/com/example/app/service/CandidateServiceTest.java"]

        self.assertIn("class CandidateServiceTest", content)
        self.assertIn("void smokeTest_compiles()", content)
        self.assertNotIn("new CandidateRequest(id, \"name\", \"email\")", content)

    def test_sanitize_removes_duplicate_test_methods_from_same_class(self):
        raw_tests = {
            "src/test/java/com/example/app/service/CandidateServiceImplTest.java": """package com.example.app.service;

import org.junit.jupiter.api.Test;

class CandidateServiceImplTest {

    @Test
    void create_nullRequest_throwsBusinessException() {
    }

    @Test
    void create_nullRequest_throwsBusinessException() {
    }
}
""",
        }

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, self.analysis)
        content = sanitized["src/test/java/com/example/app/service/CandidateServiceImplTest.java"]

        self.assertEqual(content.count("create_nullRequest_throwsBusinessException"), 1)
        self.assertIn("duplicate_test_method_removed:create_nullRequest_throwsBusinessException", self.tester._current_generation_diagnostics)

    def test_prune_tests_to_story_scope_rejects_project_imports_outside_scope(self):
        story_scope = StoryScope(
            story_id="US-TEST",
            business_files=["src/main/java/com/example/app/service/impl/CandidateServiceImpl.java"],
            test_targets=["src/main/java/com/example/app/service/impl/CandidateServiceImpl.java"],
            entrypoints=[],
            dependencies=["src/main/java/com/example/app/repository/CandidateRepository.java"],
            file_roles={
                "src/main/java/com/example/app/service/impl/CandidateServiceImpl.java": "service",
                "src/main/java/com/example/app/repository/CandidateRepository.java": "repository",
            },
        )
        test_files = {
            "src/test/java/com/example/app/service/CandidateServiceImplTest.java": """package com.example.app.service;

import com.example.app.service.impl.CandidateServiceImpl;
import org.junit.jupiter.api.Test;

class CandidateServiceImplTest {
    @Test
    void smokeTest_compiles() {}
}
""",
            "src/test/java/com/example/app/service/AuthenticationServiceImplTest.java": """package com.example.app.service;

import com.example.app.service.impl.AuthenticationServiceImpl;
import org.junit.jupiter.api.Test;

class AuthenticationServiceImplTest {
    @Test
    void smokeTest_compiles() {}
}
""",
        }

        pruned = self.tester._prune_tests_to_story_scope(test_files, story_scope)

        self.assertIn("src/test/java/com/example/app/service/CandidateServiceImplTest.java", pruned)
        self.assertNotIn("src/test/java/com/example/app/service/AuthenticationServiceImplTest.java", pruned)

    def test_drop_redundant_smoke_tests_discards_smoke_only_suite(self):
        test_files = {
            "src/test/java/com/example/app/service/CandidateServiceImplTest.java": self.tester._build_smoke_test_for_path(
                "src/test/java/com/example/app/service/CandidateServiceImplTest.java",
                self.analysis,
            )
        }

        pruned = self.tester._drop_redundant_smoke_tests(test_files)

        self.assertEqual(pruned, {})

    def test_sanitize_rewrites_deterministic_service_impl_test_with_wrong_constructor_arity(self):
        raw_tests = {
            "src/test/java/com/example/app/service/CandidateServiceImplTest.java": """package com.example.app.service;

import com.example.app.repository.CandidateRepository;
import com.example.app.service.impl.CandidateServiceImpl;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;

class CandidateServiceImplTest {

    @Mock
    private CandidateRepository repository;

    private CandidateServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new CandidateServiceImpl(repository);
    }

    @Test
    void smoke() {}
}
""",
        }

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, self.analysis)
        content = sanitized["src/test/java/com/example/app/service/CandidateServiceImplTest.java"]

        self.assertIn("class CandidateServiceImplTest", content)
        self.assertIn("void smokeTest_compiles()", content)
        self.assertNotIn("new CandidateServiceImpl(repository)", content)

    def test_sanitize_rewrites_injectmocks_service_interface_to_impl(self):
        raw_tests = {
            "src/test/java/com/example/app/service/CandidateServiceTest.java": """package com.example.app.service;

import com.example.app.repository.CandidateRepository;
import com.example.app.service.impl.CandidateServiceImpl;
import org.junit.jupiter.api.Test;
import org.mockito.InjectMocks;
import org.mockito.Mock;

class CandidateServiceTest {
    @Mock
    private CandidateRepository candidateRepository;

    @InjectMocks
    private CandidateService candidateService;

    @Test
    void smokeTest() {}
}
""",
        }

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, self.analysis)
        content = sanitized["src/test/java/com/example/app/service/CandidateServiceTest.java"]

        self.assertIn("@InjectMocks\n    private CandidateServiceImpl candidateService;", content)
        self.assertNotIn("@InjectMocks\n    private CandidateService candidateService;", content)

    def test_augment_prefers_deterministic_service_impl_tests_over_llm_variants(self):
        llm_tests = {
            "src/test/java/com/example/app/service/CandidateServiceImplTest.java": """package com.example.app.service;

import org.junit.jupiter.api.Test;

class CandidateServiceImplTest {
    @Test
    void generatedByLlm() {}
}
""",
        }

        augmented = self.tester._augment_with_project_wide_deterministic_tests(
            llm_tests,
            self.generated_code,
            self.analysis,
        )
        content = augmented["src/test/java/com/example/app/service/CandidateServiceImplTest.java"]

        self.assertIn("findAll_returnsMappedResponses", content)
        self.assertIn("create_validRequest_returnsMappedResponse", content)
        self.assertNotIn("generatedByLlm", content)

    def test_prune_shadowed_test_variants_prefers_service_impl_test_over_service_test(self):
        test_files = {
            "src/test/java/com/example/app/service/AuthenticationServiceTest.java": "class AuthenticationServiceTest {}",
            "src/test/java/com/example/app/service/AuthenticationServiceImplTest.java": "class AuthenticationServiceImplTest {}",
        }

        pruned = self.tester._prune_shadowed_test_variants(test_files)

        self.assertNotIn("src/test/java/com/example/app/service/AuthenticationServiceTest.java", pruned)
        self.assertIn("src/test/java/com/example/app/service/AuthenticationServiceImplTest.java", pruned)

    def test_deterministic_service_impl_test_uses_declared_response_fields_only(self):
        augmented = self.tester._augment_with_project_wide_deterministic_tests(
            {},
            self.generated_code,
            self.analysis,
        )
        content = augmented["src/test/java/com/example/app/service/CandidateServiceImplTest.java"]

        self.assertIn("response.getName()", content)
        self.assertNotIn("response.getId()", content)
        self.assertNotIn("responses.get(0).getId()", content)
        self.assertNotIn("responses.get(0).getName()).isEqualTo(request.getName())", content)
        self.assertIn("Candidate entity = buildEntity(1L);", content)
        self.assertIn("responses.get(0).getName()).isEqualTo(entity.getName())", content)

    def test_augment_stubs_related_repository_dependencies_for_service_impl_tests(self):
        analysis = deepcopy(self.analysis)
        analysis.entities = [
            Entity(
                name="Application",
                fields=[
                    EntityField(name="id", type="Long"),
                    EntityField(name="jobTitle", type="String"),
                    EntityField(name="status", type="String"),
                    EntityField(name="candidate", type="Candidate"),
                ],
            ),
            *analysis.entities,
        ]
        generated_code = deepcopy(self.generated_code)
        generated_code.files["src/main/java/com/example/app/dto/ApplicationRequest.java"] = """package com.example.app.dto;

public class ApplicationRequest {
    private String jobTitle;
    private String status;
    private Long candidateId;

    public void setJobTitle(String jobTitle) { this.jobTitle = jobTitle; }
    public void setStatus(String status) { this.status = status; }
    public void setCandidateId(Long candidateId) { this.candidateId = candidateId; }
    public String getJobTitle() { return jobTitle; }
    public String getStatus() { return status; }
    public Long getCandidateId() { return candidateId; }
}
"""
        generated_code.files["src/main/java/com/example/app/dto/ApplicationResponse.java"] = """package com.example.app.dto;

public class ApplicationResponse {
    private Long id;
    public Long getId() { return id; }
}
"""
        generated_code.files["src/main/java/com/example/app/service/impl/ApplicationServiceImpl.java"] = """package com.example.app.service.impl;

import com.example.app.dto.ApplicationRequest;
import com.example.app.dto.ApplicationResponse;
import com.example.app.entity.Application;
import com.example.app.repository.ApplicationRepository;
import com.example.app.repository.CandidateRepository;

public class ApplicationServiceImpl {
    private final ApplicationRepository applicationRepository;
    private final CandidateRepository candidateRepository;

    public ApplicationServiceImpl(ApplicationRepository applicationRepository, CandidateRepository candidateRepository) {
        this.applicationRepository = applicationRepository;
        this.candidateRepository = candidateRepository;
    }

    public java.util.List<ApplicationResponse> findAll() { return java.util.List.of(); }
    public ApplicationResponse findById(Long id) { return null; }
    public ApplicationResponse create(ApplicationRequest request) { return null; }
    public ApplicationResponse update(Long id, ApplicationRequest request) { return null; }
    public void delete(Long id) {}
}
"""

        augmented = self.tester._augment_with_project_wide_deterministic_tests(
            {},
            generated_code,
            analysis,
        )
        content = augmented["src/test/java/com/example/app/service/ApplicationServiceImplTest.java"]

        self.assertIn("when(candidateRepository.findById(request.getCandidateId()))", content)
        self.assertIn("thenReturn(Optional.of(buildCandidate(request.getCandidateId())))", content)
        self.assertIn("private Candidate buildCandidate(Long id)", content)

    def test_targeted_augment_focuses_on_requested_uncovered_class(self):
        targeted = self.tester._augment_with_targeted_deterministic_tests(
            {},
            self.generated_code,
            self.analysis,
            ["CandidateServiceImpl"],
        )

        self.assertIn(
            "src/test/java/com/example/app/service/CandidateServiceImplTest.java",
            targeted,
        )
        self.assertNotIn(
            "src/test/java/com/example/app/support/InfrastructureCoverageDeterministicTest.java",
            targeted,
        )

    def test_targeted_coverage_generation_disables_cache(self):
        self.tester.call_llm = AsyncMock(return_value="""```java:src/test/java/com/example/app/service/CandidateCoverageTest.java
class CandidateCoverageTest {}
```""")

        generated = asyncio.run(
            self.tester._generate_targeted_coverage_tests(
                self.generated_code,
                self.analysis,
                ["CandidateServiceImpl"],
            )
        )

        self.assertIn(
            "src/test/java/com/example/app/service/CandidateCoverageTest.java",
            generated,
        )
        self.assertEqual(self.tester.call_llm.await_args.kwargs["use_cache"], False)
        self.assertEqual(
            self.tester.call_llm.await_args.kwargs["cache_namespace"],
            "coverage_retry_targeted",
        )

    def test_story_template_tests_prioritize_service_and_controller_for_scope(self):
        story_scope = StoryScope(
            story_id="US-TEST",
            business_files=[
                "src/main/java/com/example/app/service/impl/CandidateServiceImpl.java",
                "src/main/java/com/example/app/controller/CandidateController.java",
                "src/main/java/com/example/app/repository/CandidateRepository.java",
                "src/main/java/com/example/app/entity/Candidate.java",
            ],
            test_targets=[
                "src/main/java/com/example/app/service/impl/CandidateServiceImpl.java",
                "src/main/java/com/example/app/controller/CandidateController.java",
            ],
            entrypoints=["src/main/java/com/example/app/controller/CandidateController.java"],
            dependencies=["src/main/java/com/example/app/repository/CandidateRepository.java"],
            file_roles={
                "src/main/java/com/example/app/service/impl/CandidateServiceImpl.java": "service",
                "src/main/java/com/example/app/controller/CandidateController.java": "controller",
                "src/main/java/com/example/app/repository/CandidateRepository.java": "repository",
                "src/main/java/com/example/app/entity/Candidate.java": "entity",
            },
        )
        self.generated_code.files["src/main/java/com/example/app/controller/CandidateController.java"] = """package com.example.app.controller;

import com.example.app.dto.CandidateRequest;
import com.example.app.dto.CandidateResponse;
import com.example.app.service.CandidateService;
import org.springframework.http.ResponseEntity;

public class CandidateController {
    private final CandidateService service;
    public CandidateController(CandidateService service) { this.service = service; }
    public ResponseEntity<java.util.List<CandidateResponse>> findAll() { return null; }
    public ResponseEntity<CandidateResponse> findById(Long id) { return null; }
    public ResponseEntity<CandidateResponse> create(CandidateRequest request) { return null; }
    public ResponseEntity<CandidateResponse> update(Long id, CandidateRequest request) { return null; }
    public ResponseEntity<Void> delete(Long id) { return null; }
}
"""

        generated = self.tester._generate_story_template_tests(
            self.generated_code,
            self.analysis,
            story_scope,
            target_classes=[],
            include_repository_tests=False,
        )

        self.assertIn(
            "src/test/java/com/example/app/service/CandidateServiceImplTest.java",
            generated,
        )
        self.assertIn(
            "src/test/java/com/example/app/controller/CandidateControllerDeterministicTest.java",
            generated,
        )
        self.assertNotIn(
            "src/test/java/com/example/app/repository/CandidateRepositoryDeterministicTest.java",
            generated,
        )

    def test_targeted_generation_does_not_promote_entity_targets_into_repository_tests(self):
        story_scope = StoryScope(
            story_id="US-TEST",
            business_files=[
                "src/main/java/com/example/app/service/impl/CandidateServiceImpl.java",
                "src/main/java/com/example/app/entity/Candidate.java",
            ],
            test_targets=[
                "src/main/java/com/example/app/service/impl/CandidateServiceImpl.java",
                "src/main/java/com/example/app/entity/Candidate.java",
            ],
            entrypoints=[],
            dependencies=["src/main/java/com/example/app/repository/CandidateRepository.java"],
            file_roles={
                "src/main/java/com/example/app/service/impl/CandidateServiceImpl.java": "service",
                "src/main/java/com/example/app/entity/Candidate.java": "entity",
                "src/main/java/com/example/app/repository/CandidateRepository.java": "repository",
            },
        )

        generated = self.tester._generate_deterministic_suite(
            self.generated_code,
            self.analysis,
            mode="coverage_retry_targeted",
            story_scope=story_scope,
            target_classes=["Candidate", "CandidateServiceImpl"],
            existing_test_files={},
        )

        self.assertIn(
            "src/test/java/com/example/app/service/CandidateServiceImplTest.java",
            generated,
        )
        self.assertNotIn(
            "src/test/java/com/example/app/repository/CandidateRepositoryDeterministicTest.java",
            generated,
        )

    def test_story_template_tests_build_generic_auth_service_branch_coverage_from_code_patterns(self):
        generated_code = deepcopy(self.generated_code)
        generated_code.files["src/main/java/com/example/app/dto/AuthenticationRequest.java"] = """package com.example.app.dto;

public class AuthenticationRequest {
    private String username;
    private String password;

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }
}
"""
        generated_code.files["src/main/java/com/example/app/dto/AuthenticationResponse.java"] = """package com.example.app.dto;

public class AuthenticationResponse {
    private Long id;
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
}
"""
        generated_code.files["src/main/java/com/example/app/entity/User.java"] = """package com.example.app.entity;

public class User {
    private Long id;
    private String username;
    private String password;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }
}
"""
        generated_code.files["src/main/java/com/example/app/repository/UserRepository.java"] = """package com.example.app.repository;

public interface UserRepository {
    java.util.Optional<com.example.app.entity.User> findByUsername(String username);
}
"""
        generated_code.files["src/main/java/com/example/app/service/impl/AuthenticationServiceImpl.java"] = """package com.example.app.service.impl;

import com.example.app.dto.AuthenticationRequest;
import com.example.app.dto.AuthenticationResponse;
import com.example.app.entity.User;
import com.example.app.exception.BusinessException;
import com.example.app.exception.ResourceNotFoundException;
import com.example.app.repository.UserRepository;
import org.springframework.security.crypto.password.PasswordEncoder;

public class AuthenticationServiceImpl {
    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    public AuthenticationServiceImpl(UserRepository userRepository, PasswordEncoder passwordEncoder) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
    }

    public AuthenticationResponse login(AuthenticationRequest request) {
        if (request == null || request.getUsername() == null || request.getUsername().isBlank()) {
            throw new BusinessException("username required");
        }
        if (request.getPassword() == null || request.getPassword().isBlank()) {
            throw new BusinessException("password required");
        }
        User user = userRepository.findByUsername(request.getUsername())
                .orElseThrow(() -> new ResourceNotFoundException("user"));
        if (!passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            throw new BusinessException("password mismatch");
        }
        AuthenticationResponse response = new AuthenticationResponse();
        response.setId(user.getId());
        return response;
    }
}
"""
        analysis = deepcopy(self.analysis)
        story_scope = StoryScope(
            story_id="US-TEST",
            business_files=["src/main/java/com/example/app/service/impl/AuthenticationServiceImpl.java"],
            test_targets=["src/main/java/com/example/app/service/impl/AuthenticationServiceImpl.java"],
            entrypoints=[],
            dependencies=["src/main/java/com/example/app/repository/UserRepository.java"],
            file_roles={
                "src/main/java/com/example/app/service/impl/AuthenticationServiceImpl.java": "service",
                "src/main/java/com/example/app/repository/UserRepository.java": "repository",
            },
        )

        generated = self.tester._generate_story_template_tests(
            generated_code,
            analysis,
            story_scope,
            target_classes=["AuthenticationServiceImpl"],
            include_repository_tests=False,
        )
        content = generated["src/test/java/com/example/app/service/AuthenticationServiceImplTest.java"]

        self.assertIn("login_userNotFound_throwsResourceNotFoundException", content)
        self.assertIn("login_blankUsername_throwsBusinessException", content)
        self.assertIn("login_blankPassword_throwsBusinessException", content)
        self.assertIn("login_passwordMismatch_throwsBusinessException", content)
        self.assertIn("when(userRepository.findByUsername(request.getUsername()))", content)
        self.assertIn("when(passwordEncoder.matches(request.getPassword(), entity.getPassword()))", content)

    def test_story_template_tests_detect_generic_optional_and_validation_guards_on_other_service_impl(self):
        generated_code = deepcopy(self.generated_code)
        generated_code.files["src/main/java/com/example/app/dto/ApplicationRequest.java"] = """package com.example.app.dto;

public class ApplicationRequest {
    private String jobTitle;
    private Long candidateId;

    public String getJobTitle() { return jobTitle; }
    public void setJobTitle(String jobTitle) { this.jobTitle = jobTitle; }
    public Long getCandidateId() { return candidateId; }
    public void setCandidateId(Long candidateId) { this.candidateId = candidateId; }
}
"""
        generated_code.files["src/main/java/com/example/app/dto/ApplicationResponse.java"] = """package com.example.app.dto;

public class ApplicationResponse {
    private Long id;
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
}
"""
        generated_code.files["src/main/java/com/example/app/entity/Application.java"] = """package com.example.app.entity;

public class Application {
    private Long id;
    private String jobTitle;
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getJobTitle() { return jobTitle; }
    public void setJobTitle(String jobTitle) { this.jobTitle = jobTitle; }
}
"""
        generated_code.files["src/main/java/com/example/app/entity/Candidate.java"] = """package com.example.app.entity;

public class Candidate {
    private Long id;
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
}
"""
        generated_code.files["src/main/java/com/example/app/repository/ApplicationRepository.java"] = """package com.example.app.repository;

public interface ApplicationRepository {
    com.example.app.entity.Application save(com.example.app.entity.Application application);
}
"""
        generated_code.files["src/main/java/com/example/app/repository/CandidateRepository.java"] = """package com.example.app.repository;

public interface CandidateRepository {
    java.util.Optional<com.example.app.entity.Candidate> findById(Long id);
    boolean existsById(Long id);
}
"""
        generated_code.files["src/main/java/com/example/app/service/impl/ApplicationServiceImpl.java"] = """package com.example.app.service.impl;

import com.example.app.dto.ApplicationRequest;
import com.example.app.dto.ApplicationResponse;
import com.example.app.entity.Application;
import com.example.app.entity.Candidate;
import com.example.app.exception.BusinessException;
import com.example.app.exception.ResourceNotFoundException;
import com.example.app.repository.ApplicationRepository;
import com.example.app.repository.CandidateRepository;

public class ApplicationServiceImpl {
    private final ApplicationRepository applicationRepository;
    private final CandidateRepository candidateRepository;

    public ApplicationServiceImpl(ApplicationRepository applicationRepository, CandidateRepository candidateRepository) {
        this.applicationRepository = applicationRepository;
        this.candidateRepository = candidateRepository;
    }

    public ApplicationResponse create(ApplicationRequest request) {
        if (request == null) {
            throw new BusinessException("request required");
        }
        if (request.getJobTitle() == null || request.getJobTitle().isBlank()) {
            throw new BusinessException("jobTitle required");
        }
        Candidate candidate = candidateRepository.findById(request.getCandidateId())
                .orElseThrow(() -> new ResourceNotFoundException("candidate"));
        if (!candidateRepository.existsById(request.getCandidateId())) {
            throw new BusinessException("candidate inactive");
        }
        Application saved = applicationRepository.save(new Application());
        ApplicationResponse response = new ApplicationResponse();
        response.setId(saved.getId());
        return response;
    }
}
"""
        analysis = deepcopy(self.analysis)
        story_scope = StoryScope(
            story_id="US-TEST",
            business_files=["src/main/java/com/example/app/service/impl/ApplicationServiceImpl.java"],
            test_targets=["src/main/java/com/example/app/service/impl/ApplicationServiceImpl.java"],
            entrypoints=[],
            dependencies=[
                "src/main/java/com/example/app/repository/ApplicationRepository.java",
                "src/main/java/com/example/app/repository/CandidateRepository.java",
            ],
            file_roles={
                "src/main/java/com/example/app/service/impl/ApplicationServiceImpl.java": "service",
                "src/main/java/com/example/app/repository/ApplicationRepository.java": "repository",
                "src/main/java/com/example/app/repository/CandidateRepository.java": "repository",
            },
        )

        generated = self.tester._generate_story_template_tests(
            generated_code,
            analysis,
            story_scope,
            target_classes=["ApplicationServiceImpl"],
            include_repository_tests=False,
        )
        content = generated["src/test/java/com/example/app/service/ApplicationServiceImplTest.java"]

        self.assertIn("create_nullRequest_throwsBusinessException", content)
        self.assertIn("create_nullJobTitle_throwsBusinessException", content)
        self.assertIn("create_blankJobTitle_throwsBusinessException", content)
        self.assertIn("create_missingCandidate_throwsResourceNotFoundException", content)
        self.assertIn("create_ExistsByIdFalse_throwsBusinessException", content)
        self.assertIn("when(candidateRepository.findById(request.getCandidateId())).thenReturn(Optional.empty())", content)
        self.assertIn("when(candidateRepository.existsById(request.getCandidateId())).thenReturn(false)", content)

    def test_story_template_tests_detect_custom_exception_comparison_guards(self):
        generated_code = deepcopy(self.generated_code)
        generated_code.files["src/main/java/com/example/app/dto/OfferRequest.java"] = """package com.example.app.dto;

public class OfferRequest {
    private Long salary;
    private String contractType;

    public Long getSalary() { return salary; }
    public void setSalary(Long salary) { this.salary = salary; }
    public String getContractType() { return contractType; }
    public void setContractType(String contractType) { this.contractType = contractType; }
}
"""
        generated_code.files["src/main/java/com/example/app/dto/OfferResponse.java"] = """package com.example.app.dto;

public class OfferResponse {
    private Long id;
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
}
"""
        generated_code.files["src/main/java/com/example/app/entity/Offer.java"] = """package com.example.app.entity;

public class Offer {
    private Long id;
    private Long salary;
    private String contractType;
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getSalary() { return salary; }
    public void setSalary(Long salary) { this.salary = salary; }
    public String getContractType() { return contractType; }
    public void setContractType(String contractType) { this.contractType = contractType; }
}
"""
        generated_code.files["src/main/java/com/example/app/repository/OfferRepository.java"] = """package com.example.app.repository;

public interface OfferRepository {
    com.example.app.entity.Offer save(com.example.app.entity.Offer offer);
}
"""
        generated_code.files["src/main/java/com/example/app/exception/DomainValidationException.java"] = """package com.example.app.exception;

public class DomainValidationException extends RuntimeException {
    public DomainValidationException(String message) { super(message); }
}
"""
        generated_code.files["src/main/java/com/example/app/service/impl/OfferServiceImpl.java"] = """package com.example.app.service.impl;

import com.example.app.dto.OfferRequest;
import com.example.app.dto.OfferResponse;
import com.example.app.entity.Offer;
import com.example.app.exception.DomainValidationException;
import com.example.app.repository.OfferRepository;

public class OfferServiceImpl {
    private final OfferRepository offerRepository;

    public OfferServiceImpl(OfferRepository offerRepository) {
        this.offerRepository = offerRepository;
    }

    public OfferResponse create(OfferRequest request) {
        if (request.getSalary() <= 0L) {
            throw new DomainValidationException("salary must be positive");
        }
        if (request.getContractType().equals("ARCHIVED")) {
            throw new DomainValidationException("contract type invalid");
        }
        Offer saved = offerRepository.save(new Offer());
        OfferResponse response = new OfferResponse();
        response.setId(saved.getId());
        return response;
    }
}
"""
        analysis = deepcopy(self.analysis)
        story_scope = StoryScope(
            story_id="US-TEST",
            business_files=["src/main/java/com/example/app/service/impl/OfferServiceImpl.java"],
            test_targets=["src/main/java/com/example/app/service/impl/OfferServiceImpl.java"],
            entrypoints=[],
            dependencies=["src/main/java/com/example/app/repository/OfferRepository.java"],
            file_roles={
                "src/main/java/com/example/app/service/impl/OfferServiceImpl.java": "service",
                "src/main/java/com/example/app/repository/OfferRepository.java": "repository",
            },
        )

        generated = self.tester._generate_story_template_tests(
            generated_code,
            analysis,
            story_scope,
            target_classes=["OfferServiceImpl"],
            include_repository_tests=False,
        )
        content = generated["src/test/java/com/example/app/service/OfferServiceImplTest.java"]

        self.assertIn("create_invalidSalary_throwsDomainValidationException", content)
        self.assertIn("request.setSalary(0L);", content)
        self.assertIn("create_invalidContractType_throwsDomainValidationException", content)
        self.assertIn('request.setContractType("ARCHIVED");', content)

    def test_sanitize_rejects_non_test_retry_files(self):
        raw_tests = {
            "src/test/java/com/example/app/service/impl/UserRepositoryImpl.java": """package com.example.app.service.impl;
public class UserRepositoryImpl {}
""",
        }

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, self.analysis)

        self.assertNotIn(
            "src/test/java/com/example/app/service/impl/UserRepositoryImpl.java",
            sanitized,
        )
        self.assertIn("invalid_test_file", " ".join(self.tester._current_generation_diagnostics))

    def test_sanitize_does_not_globally_rewrite_name_accessors_from_unrelated_entities(self):
        analysis = deepcopy(self.analysis)
        analysis.entities = [
            Entity(
                name="Application",
                fields=[
                    EntityField(name="id", type="Long"),
                    EntityField(name="jobTitle", type="String"),
                    EntityField(name="status", type="String"),
                ],
            ),
            *analysis.entities,
        ]

        raw_tests = {
            "src/test/java/com/example/app/service/CandidateServiceImplTest.java": """package com.example.app.service;

import com.example.app.dto.CandidateRequest;
import org.junit.jupiter.api.Test;

class CandidateServiceImplTest {

    @Test
    void preservesCandidateNameAccessors() {
        CandidateRequest request = new CandidateRequest();
        request.setName("Jane Doe");
    }
}
""",
        }

        sanitized = self.tester._sanitize_generated_tests(raw_tests, self.generated_code, analysis)
        content = sanitized["src/test/java/com/example/app/service/CandidateServiceImplTest.java"]

        self.assertIn('request.setName("Jane Doe");', content)
        self.assertNotIn("request.setJobTitle", content)
        self.assertNotIn("request.setStatus", content)

    def test_maven_writer_defensively_rewrites_main_java_test_paths(self):
        runner = MavenBuildRunner()
        with tempfile.TemporaryDirectory() as tmp:
            written = runner._write_test_sources(
                {
                    "src/main/java/com/example/app/controller/CandidateControllerTest.java": "class CandidateControllerTest {}"
                },
                Path(tmp),
            )
            self.assertEqual(
                written,
                ["src/test/java/com/example/app/controller/CandidateControllerTest.java"],
            )
            self.assertTrue(
                Path(tmp, "src/test/java/com/example/app/controller/CandidateControllerTest.java").exists()
            )

    def test_classify_test_failure_prefers_execution_failure_when_tests_actually_error(self):
        runner = MavenBuildRunner()

        failure_type = runner._classify_test_failure(
            output="[ERROR] Tests run: 39, Errors: 2, Skipped: 0 on JDK 21",
            returncode=1,
            failed_tests=0,
            error_tests=2,
            total_tests=39,
            surefire_report_issue=None,
        )

        self.assertEqual(failure_type, "test_execution_failure")


if __name__ == "__main__":
    unittest.main()
