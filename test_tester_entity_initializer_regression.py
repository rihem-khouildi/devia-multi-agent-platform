import unittest
from copy import deepcopy

from agents.tester import TesterAgent
from config.settings import HuggingFaceConfig
from core.models import AnalysisResult, Entity, EntityField, GeneratedCode


class TesterEntityInitializerRegressionTest(unittest.TestCase):
    def setUp(self):
        self.tester = TesterAgent(HuggingFaceConfig())
        self.analysis = AnalysisResult(
            entities=[
                Entity(
                    name="Application",
                    fields=[
                        EntityField(name="id", type="Long"),
                        EntityField(name="jobTitle", type="String"),
                        EntityField(name="status", type="String"),
                        EntityField(name="candidate", type="Candidate"),
                    ],
                ),
                Entity(
                    name="Candidate",
                    fields=[
                        EntityField(name="id", type="Long"),
                        EntityField(name="name", type="String"),
                        EntityField(name="email", type="String"),
                        EntityField(name="address", type="String"),
                    ],
                ),
            ],
            endpoints=[],
            gherkin_scenarios=[],
            architecture_notes="",
            package_base="com.example.app",
            service_name="Application",
        )
        self.generated_code = GeneratedCode(
            files={
                "src/main/java/com/example/app/entity/Application.java": """package com.example.app.entity;

public class Application {
    private Long id;
    private String jobTitle;
    private String status;
    private Candidate candidate;

    public void setId(Long id) { this.id = id; }
    public void setJobTitle(String jobTitle) { this.jobTitle = jobTitle; }
    public void setStatus(String status) { this.status = status; }
    public void setCandidate(Candidate candidate) { this.candidate = candidate; }
}
""",
                "src/main/java/com/example/app/entity/Candidate.java": """package com.example.app.entity;

public class Candidate {
    private Long id;
    private String name;
    private String email;
    private String address;

    public void setId(Long id) { this.id = id; }
    public void setName(String name) { this.name = name; }
    public void setEmail(String email) { this.email = email; }
    public void setAddress(String address) { this.address = address; }
}
""",
                "src/main/java/com/example/app/dto/ApplicationRequest.java": """package com.example.app.dto;

public class ApplicationRequest {
    private String jobTitle;
    private String status;
    private Long candidateId;

    public void setJobTitle(String jobTitle) { this.jobTitle = jobTitle; }
    public void setStatus(String status) { this.status = status; }
    public void setCandidateId(Long candidateId) { this.candidateId = candidateId; }
    public Long getCandidateId() { return candidateId; }
}
""",
                "src/main/java/com/example/app/dto/ApplicationResponse.java": """package com.example.app.dto;

public class ApplicationResponse {
    private Long id;
    public Long getId() { return id; }
}
""",
                "src/main/java/com/example/app/exception/BusinessException.java": """package com.example.app.exception;

public class BusinessException extends RuntimeException {
    public BusinessException(String message) {
        super(message);
    }
}
""",
                "src/main/java/com/example/app/exception/ResourceNotFoundException.java": """package com.example.app.exception;

public class ResourceNotFoundException extends RuntimeException {
    public ResourceNotFoundException(String resource, String field, Object value) {
        super(resource + field + value);
    }
}
""",
                "src/main/java/com/example/app/repository/ApplicationRepository.java": """package com.example.app.repository;

import com.example.app.entity.Application;
import java.util.List;
import java.util.Optional;

public interface ApplicationRepository {
    List<Application> findAll();
    Optional<Application> findById(Long id);
    Application save(Application entity);
    void delete(Application entity);
}
""",
                "src/main/java/com/example/app/repository/CandidateRepository.java": """package com.example.app.repository;

import com.example.app.entity.Candidate;
import java.util.Optional;

public interface CandidateRepository {
    Optional<Candidate> findById(Long id);
}
""",
                "src/main/java/com/example/app/service/impl/ApplicationServiceImpl.java": """package com.example.app.service.impl;

import com.example.app.repository.ApplicationRepository;
import com.example.app.repository.CandidateRepository;

public class ApplicationServiceImpl {
    private final ApplicationRepository applicationRepository;
    private final CandidateRepository candidateRepository;

    public ApplicationServiceImpl(ApplicationRepository applicationRepository, CandidateRepository candidateRepository) {
        this.applicationRepository = applicationRepository;
        this.candidateRepository = candidateRepository;
    }

    public java.util.List<Object> findAll() { return java.util.List.of(); }
    public Object findById(Long id) { return null; }
    public Object create(Object request) { return null; }
    public Object update(Long id, Object request) { return null; }
    public void delete(Long id) {}
}
""",
            },
            pom_xml="",
        )

    def test_sanitize_keeps_application_service_impl_test_when_auxiliary_entity_helper_exists(self):
        resource = {
            "resource_name": "Application",
            "package_name": "com.example.app",
            "service_impl_name": "ApplicationServiceImpl",
            "service_name": "ApplicationService",
            "controller_name": "ApplicationController",
            "repository_name": "ApplicationRepository",
            "request_name": "ApplicationRequest",
            "response_name": "ApplicationResponse",
            "entity_name": "Application",
            "dependencies": [
                {"type": "ApplicationRepository", "name": "applicationRepository"},
                {"type": "CandidateRepository", "name": "candidateRepository"},
            ],
            "all_field_specs": {
                "Application": [("id", "Long"), ("jobTitle", "String"), ("status", "String"), ("candidate", "Candidate")],
                "Candidate": [("id", "Long"), ("name", "String"), ("email", "String"), ("address", "String")],
                "ApplicationRequest": [("jobTitle", "String"), ("status", "String"), ("candidateId", "Long")],
            },
            "request_fields": [("jobTitle", "String"), ("status", "String"), ("candidateId", "Long")],
            "entity_fields": [("id", "Long"), ("jobTitle", "String"), ("status", "String"), ("candidate", "Candidate")],
            "has_controller": False,
            "has_repository": True,
        }

        path, content = self.tester._build_service_impl_test(resource)
        sanitized = self.tester._sanitize_generated_tests(
            {path: content},
            deepcopy(self.generated_code),
            deepcopy(self.analysis),
        )

        kept = sanitized[path]
        self.assertIn("buildCandidate", kept)
        self.assertIn("Application application = new Application();", kept)
        self.assertIn("Candidate candidate = new Candidate();", kept)
        self.assertNotIn("smokeTest_compiles", kept)


if __name__ == "__main__":
    unittest.main()
