package com.giftfuture.chinapubcf.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class NavigationController {
    @GetMapping({"/", "/index.jsp"})
    public String index() {
        return "redirect:/index.html";
    }

    @GetMapping("/recommander.jsp")
    public String recommendations() {
        return "redirect:/recommander.html";
    }
}
