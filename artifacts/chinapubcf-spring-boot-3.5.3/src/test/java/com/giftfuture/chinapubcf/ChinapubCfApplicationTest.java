package com.giftfuture.chinapubcf;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

import java.util.concurrent.atomic.AtomicInteger;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ChinapubCfApplicationTest {
    private static final AtomicInteger IDS = new AtomicInteger();

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;

    @Test
    void applicationStartsAndExposesHealthAndStaticUi() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
        mvc.perform(get("/index.html"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("Spring Boot 3.5.3")));
        mvc.perform(get("/index.jsp"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/index.html"));
    }

    @Test
    void listsBooksAndPreservesPagingSessionContract() throws Exception {
        MockHttpSession session = new MockHttpSession();
        mvc.perform(get("/books").param("pageno", "1").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(10)))
                .andExpect(jsonPath("$[0].bookId").value(1));
        org.junit.jupiter.api.Assertions.assertEquals(1, session.getAttribute("pageno"));
        org.junit.jupiter.api.Assertions.assertEquals(23L, session.getAttribute("bookCount"));
        org.junit.jupiter.api.Assertions.assertEquals(3L, session.getAttribute("allpages"));
    }

    @Test
    void registrationUsesStrongHashAndNeverReturnsCredentials() throws Exception {
        String login = nextLogin();
        String response = mvc.perform(post("/register")
                        .param("name", login)
                        .param("email", login + "@example.test")
                        .param("usrpwd", "safe-pass-123"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value(login))
                .andExpect(content().string(not(containsString("password"))))
                .andReturn().getResponse().getContentAsString();
        JsonNode user = json.readTree(response);
        org.junit.jupiter.api.Assertions.assertTrue(user.get("userId").asLong() > 0);
    }

    @Test
    void loginBindsSessionWithoutStoringPasswordAndSupportsSessionLookup() throws Exception {
        Account account = registerAndLogin("login");
        org.junit.jupiter.api.Assertions.assertNull(account.session().getAttribute("usrpwd"));
        mvc.perform(get("/sessionlogin").session(account.session()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(account.userId()))
                .andExpect(content().string(not(containsString("password"))));
    }

    @Test
    void verifiedLegacyMd5LoginIsUpgradedToBcryptEvenForHistoricShortPassword() throws Exception {
        mvc.perform(post("/user")
                        .param("email", "matrix@matrix.com")
                        .param("usrpwd", "matrix"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(1))
                .andExpect(content().string(not(containsString("password"))));
        String upgraded = jdbc.queryForObject(
                "SELECT password_hash FROM app_user WHERE user_id = 1", String.class);
        org.junit.jupiter.api.Assertions.assertNotNull(upgraded);
        org.junit.jupiter.api.Assertions.assertTrue(upgraded.startsWith("$2"));
    }

    @Test
    void invalidAndSqlInjectionCredentialsFailClosed() throws Exception {
        String login = nextLogin();
        register(login, "safe-pass-123");
        mvc.perform(post("/user").param("email", "' OR 1=1 --").param("usrpwd", "anything"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/user").param("email", login).param("usrpwd", "wrong-password"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ratingRequiresSessionAndRejectsCrossUserWrites() throws Exception {
        Account first = registerAndLogin("owner");
        Account second = registerAndLogin("other");
        mvc.perform(post("/rating").param("userId", Long.toString(first.userId()))
                        .param("bookIdScores", "1-5"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/rating").session(first.session())
                        .param("userId", Long.toString(second.userId()))
                        .param("bookIdScores", "1-5"))
                .andExpect(status().isForbidden());
    }

    @Test
    void ratingsAndPurchasedBooksRoundTripThroughLegacyUrls() throws Exception {
        Account account = registerAndLogin("ratings");
        mvc.perform(post("/RatingServlet").session(account.session())
                        .param("userId", Long.toString(account.userId()))
                        .param("bookIdScores", "1-5,2-4.5"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.recorded").value(2));
        mvc.perform(get("/booklist").session(account.session())
                        .param("userId", Long.toString(account.userId())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)))
                .andExpect(jsonPath("$[0].book.bookId").exists());
    }

    @Test
    void invalidRatingBatchDoesNotPartiallyPersist() throws Exception {
        Account account = registerAndLogin("atomic");
        mvc.perform(post("/rating").session(account.session())
                        .param("userId", Long.toString(account.userId()))
                        .param("bookIdScores", "1-5,999-4"))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/booklist").session(account.session())
                        .param("userId", Long.toString(account.userId())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(0)));
    }

    @Test
    void allRecommendationAlgorithmsSupportJsonXmlAndText() throws Exception {
        Account account = registerAndLogin("recommend");
        mvc.perform(post("/rating").session(account.session())
                        .param("userId", Long.toString(account.userId()))
                        .param("bookIdScores", "1-5,2-4"))
                .andExpect(status().isOk());
        mvc.perform(get("/userrecmd").session(account.session())
                        .param("userId", Long.toString(account.userId())).param("count", "2")
                        .param("format", "json"))
                .andExpect(status().isOk())
                .andExpect(header().string("Cache-Control", containsString("no-store")))
                .andExpect(jsonPath("$", hasSize(2)));
        mvc.perform(get("/itemrecmd").session(account.session())
                        .param("userId", Long.toString(account.userId())).param("count", "2")
                        .param("format", "xml"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("<recommendedItems>")));
        mvc.perform(get("/sloperecmd").session(account.session())
                        .param("userId", Long.toString(account.userId())).param("count", "2")
                        .param("format", "text"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("Book:")));
        mvc.perform(get("/ChinapubRecommanderServlet").session(account.session())
                        .param("userId", Long.toString(account.userId())).param("count", "2")
                        .param("format", "json"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)));
    }

    @Test
    void logoutInvalidatesSession() throws Exception {
        Account account = registerAndLogin("logout");
        mvc.perform(post("/LogoutServlet").session(account.session()))
                .andExpect(status().isNoContent());
        mvc.perform(get("/sessionlogin").session(new MockHttpSession()))
                .andExpect(status().isUnauthorized());
    }

    private Account registerAndLogin(String prefix) throws Exception {
        String login = prefix + IDS.incrementAndGet();
        long userId = register(login, "safe-pass-123");
        MockHttpSession session = new MockHttpSession();
        mvc.perform(post("/user").session(session)
                        .param("email", login + "@example.test").param("usrpwd", "safe-pass-123"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(userId));
        return new Account(userId, session);
    }

    private long register(String login, String password) throws Exception {
        String response = mvc.perform(post("/register")
                        .param("name", login)
                        .param("email", login + "@example.test")
                        .param("usrpwd", password))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return json.readTree(response).get("userId").asLong();
    }

    private static String nextLogin() {
        return "user" + IDS.incrementAndGet();
    }

    private record Account(long userId, MockHttpSession session) {
    }
}
