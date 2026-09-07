package io.elmos.controlplane;

import io.elmos.application.BatchOneDemoService;
import io.elmos.application.DemoRunResult;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/demo-runs")
public class DemoController {
    private final BatchOneDemoService service;
    public DemoController(BatchOneDemoService service){this.service=service;}
    @PostMapping @ResponseStatus(HttpStatus.CREATED) public DemoRunResult create(){return service.execute();}
}

