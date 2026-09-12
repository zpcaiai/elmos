package com.giftfuture.chinapubcf;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

import java.util.concurrent.atomic.AtomicInteger;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ChinapubCfComprehensiveApiTest {
    private static final AtomicInteger COUNTER = new AtomicInteger(100);

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;

    // --- 1. Books & Pagination Edge Cases ---

    @Test
    @DisplayName("Books pagination: zero or negative pageno returns 400 Bad Request")
    void booksRejectsInvalidPageNumbers() throws Exception {
        mvc.perform(get("/books").param("pageno", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail", containsString("pageno must be positive")));

        mvc.perform(get("/books").param("pageno", "-5"))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("Books pagination: non-numeric pageno returns 400 Bad Request")
    void booksRejectsNonNumericPageNumber() throws Exception {
        mvc.perform(get("/books").param("pageno", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("Books pagination: page beyond total pages returns empty list and updates session")
    void booksBeyondRangeReturnsEmptyList() throws Exception {
        MockHttpSession session = new MockHttpSession();
        mvc.perform(get("/books").param("pageno", "999").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(0)));

        assertEquals(999, session.getAttribute("pageno"));
        assertEquals(23L, session.getAttribute("bookCount"));
    }

    @Test
    @DisplayName("Books pagination: POST /books alias works identically")
    void booksPostAliasWorksIdentically() throws Exception {
        mvc.perform(post("/books").param("pageno", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(10)))
                .andExpect(jsonPath("$[0].bookId").value(1));
    }

    // --- 2. Registration Validation & Input Boundary Tests ---

    @Test
    @DisplayName("Registration: name too short (< 4 chars) returns 400")
    void registrationRejectsShortName() throws Exception {
        mvc.perform(post("/register")
                        .param("name", "abc")
                        .param("email", "valid@example.test")
                        .param("usrpwd", "secret123"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail", containsString("name must contain 4-20 letters")));
    }

    @Test
    @DisplayName("Registration: name too long (> 20 chars) returns 400")
    void registrationRejectsLongName() throws Exception {
        mvc.perform(post("/register")
                        .param("name", "this_username_is_way_too_long_for_policy")
                        .param("email", "valid@example.test")
                        .param("usrpwd", "secret123"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail", containsString("name must contain 4-20 letters")));
    }

    @Test
    @DisplayName("Registration: name with invalid special characters returns 400")
    void registrationRejectsInvalidNameCharacters() throws Exception {
        mvc.perform(post("/register")
                        .param("name", "bad<user>!")
                        .param("email", "valid@example.test")
                        .param("usrpwd", "secret123"))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("Registration: invalid email format returns 400")
    void registrationRejectsInvalidEmail() throws Exception {
        mvc.perform(post("/register")
                        .param("name", "validuser" + COUNTER.incrementAndGet())
                        .param("email", "not-an-email")
                        .param("usrpwd", "secret123"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail", containsString("email is invalid")));
    }

    @Test
    @DisplayName("Registration: legacy GET /RegisterServlet works and creates user")
    void legacyGetRegisterServletWorks() throws Exception {
        String name = "legreg" + COUNTER.incrementAndGet();
        mvc.perform(get("/RegisterServlet")
                        .param("name", name)
                        .param("email", name + "@legacy.test")
                        .param("usrpwd", "secret123"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value(name))
                .andExpect(jsonPath("$.email").value(name + "@legacy.test"));
    }

    // --- 3. Authentication, Password Upgrade & Session Security ---

    @Test
    @DisplayName("Login: GET /user legacy endpoint works")
    void legacyGetLoginWorks() throws Exception {
        mvc.perform(get("/user")
                        .param("email", "matrix@matrix.com")
                        .param("usrpwd", "matrix"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(1))
                .andExpect(jsonPath("$.email").value("matrix@matrix.com"));
    }

    @Test
    @DisplayName("Login: unknown username returns 401 Unauthorized")
    void loginUnknownUserFails() throws Exception {
        mvc.perform(post("/user")
                        .param("email", "nonexistent@nowhere.test")
                        .param("usrpwd", "password"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("Session: unauthenticated call to /SessionLoginServlet returns 401")
    void sessionLoginWithoutAuthFails() throws Exception {
        mvc.perform(get("/SessionLoginServlet"))
                .andExpect(status().isUnauthorized());

        mvc.perform(post("/SessionLoginServlet"))
                .andExpect(status().isUnauthorized());
    }

    // --- 4. Rating Service Robustness & Boundary Tests ---

    @Test
    @DisplayName("Rating: blank or null bookIdScores returns 400")
    void ratingRejectsBlankScores() throws Exception {
        UserSession user = createAndLogin("rateblank");
        mvc.perform(post("/rating").session(user.session)
                        .param("userId", String.valueOf(user.userId))
                        .param("bookIdScores", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail", containsString("bookIdScores is required")));
    }

    @Test
    @DisplayName("Rating: malformed token (missing hyphen) returns 400")
    void ratingRejectsMalformedToken() throws Exception {
        UserSession user = createAndLogin("ratemalformed");
        mvc.perform(post("/rating").session(user.session)
                        .param("userId", String.valueOf(user.userId))
                        .param("bookIdScores", "1_5"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail", containsString("each rating must use bookId-score format")));
    }

    @Test
    @DisplayName("Rating: non-existent book ID returns 400 Bad Request")
    void ratingRejectsNonExistentBook() throws Exception {
        UserSession user = createAndLogin("ratemissingbook");
        mvc.perform(post("/rating").session(user.session)
                        .param("userId", String.valueOf(user.userId))
                        .param("bookIdScores", "99999-5.0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail", containsString("one or more books do not exist")));
    }

    @Test
    @DisplayName("Rating: duplicate book ID in same batch returns 400")
    void ratingRejectsDuplicateBooksInBatch() throws Exception {
        UserSession user = createAndLogin("ratedup");
        mvc.perform(post("/rating").session(user.session)
                        .param("userId", String.valueOf(user.userId))
                        .param("bookIdScores", "1-4.0,1-5.0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail", containsString("duplicate book ratings are not allowed")));
    }

    @Test
    @DisplayName("Rating: legacy GET /rating endpoint records rating successfully")
    void ratingLegacyGetWorks() throws Exception {
        UserSession user = createAndLogin("rateget");
        mvc.perform(get("/rating").session(user.session)
                        .param("userId", String.valueOf(user.userId))
                        .param("bookIdScores", "1-4.5"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.recorded").value(1));
    }

    // --- 5. Purchased Books / Booklist Endpoint ---

    @Test
    @DisplayName("Booklist: unauthenticated call returns 401")
    void booklistUnauthenticatedFails() throws Exception {
        mvc.perform(get("/booklist").param("userId", "1"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("Booklist: cross-user access returns 403 Forbidden")
    void booklistCrossUserFails() throws Exception {
        UserSession user1 = createAndLogin("bluser1");
        UserSession user2 = createAndLogin("bluser2");

        mvc.perform(get("/booklist").session(user1.session)
                        .param("userId", String.valueOf(user2.userId)))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("Booklist: user with no ratings returns empty list")
    void booklistForNewUserReturnsEmptyList() throws Exception {
        UserSession user = createAndLogin("blnew");
        mvc.perform(get("/booklist").session(user.session)
                        .param("userId", String.valueOf(user.userId)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(0)));
    }

    @Test
    @DisplayName("Booklist: POST /booklist alias works identically")
    void booklistPostAliasWorks() throws Exception {
        UserSession user = createAndLogin("blpost");
        mvc.perform(post("/rating").session(user.session)
                        .param("userId", String.valueOf(user.userId))
                        .param("bookIdScores", "2-5.0"))
                .andExpect(status().isOk());

        mvc.perform(post("/booklist").session(user.session)
                        .param("userId", String.valueOf(user.userId)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].book.bookId").value(2));
    }

    // --- 6. Recommendation Algorithms, Multiple Formats & Protocol Aliases ---

    @Test
    @DisplayName("Recommendations: unsupported format returns 400 Bad Request")
    void recommendationRejectsUnsupportedFormat() throws Exception {
        UserSession user = createAndLogin("recmdformat");
        mvc.perform(get("/userrecmd").session(user.session)
                        .param("userId", String.valueOf(user.userId))
                        .param("format", "yaml"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail", containsString("format must be text, json, or xml")));
    }

    @Test
    @DisplayName("Recommendations: all 4 endpoints support POST method")
    void allRecommendationEndpointsSupportPost() throws Exception {
        UserSession user = createAndLogin("recmdpost");
        mvc.perform(post("/rating").session(user.session)
                        .param("userId", String.valueOf(user.userId))
                        .param("bookIdScores", "1-5.0,2-4.0"))
                .andExpect(status().isOk());

        mvc.perform(post("/userrecmd").session(user.session)
                        .param("userId", String.valueOf(user.userId)).param("format", "json"))
                .andExpect(status().isOk())
                .andExpect(header().string("Cache-Control", containsString("no-store")));

        mvc.perform(post("/itemrecmd").session(user.session)
                        .param("userId", String.valueOf(user.userId)).param("format", "json"))
                .andExpect(status().isOk());

        mvc.perform(post("/sloperecmd").session(user.session)
                        .param("userId", String.valueOf(user.userId)).param("format", "json"))
                .andExpect(status().isOk());

        mvc.perform(post("/chinapub").session(user.session)
                        .param("userId", String.valueOf(user.userId)).param("format", "json"))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("Recommendations: XML and Text output validation across algorithms")
    void recommendationsOutputFormatValidation() throws Exception {
        UserSession user = createAndLogin("recmdtypes");
        mvc.perform(post("/rating").session(user.session)
                        .param("userId", String.valueOf(user.userId))
                        .param("bookIdScores", "1-5.0,2-3.0,3-4.0"))
                .andExpect(status().isOk());

        // XML output structure
        mvc.perform(get("/chinapub").session(user.session)
                        .param("userId", String.valueOf(user.userId)).param("format", "xml"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_XML))
                .andExpect(content().string(containsString("<?xml version=\"1.0\" encoding=\"UTF-8\"?><recommendedItems>")));

        // Text output structure
        mvc.perform(get("/userrecmd").session(user.session)
                        .param("userId", String.valueOf(user.userId)).param("format", "text"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_PLAIN));
    }

    // --- 7. Navigation & JSP Compatibility Redirections ---

    @Test
    @DisplayName("Navigation: JSP redirects preserve historical entry URLs")
    void jspRedirectsPreserveEntryUrls() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/index.html"));

        mvc.perform(get("/index.jsp"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/index.html"));

        mvc.perform(get("/recommander.jsp"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/recommander.html"));
    }

    // --- 8. Static Web Assets Verification ---

    @Test
    @DisplayName("Static assets: HTML, CSS, JS are available and properly served")
    void staticAssetsAreServed() throws Exception {
        mvc.perform(get("/index.html")).andExpect(status().isOk());
        mvc.perform(get("/register.html")).andExpect(status().isOk());
        mvc.perform(get("/recommander.html")).andExpect(status().isOk());
        mvc.perform(get("/script/app.js")).andExpect(status().isOk());
        mvc.perform(get("/style/app.css")).andExpect(status().isOk());
    }

    // --- Helper Methods ---

    private UserSession createAndLogin(String prefix) throws Exception {
        String username = prefix + COUNTER.incrementAndGet();
        String email = username + "@test.local";
        String password = "StrongPass!" + COUNTER.get();

        String regJson = mvc.perform(post("/register")
                        .param("name", username)
                        .param("email", email)
                        .param("usrpwd", password))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();

        long userId = json.readTree(regJson).get("userId").asLong();

        MockHttpSession session = new MockHttpSession();
        mvc.perform(post("/user").session(session)
                        .param("email", email)
                        .param("usrpwd", password))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(userId));

        return new UserSession(userId, username, session);
    }

    private record UserSession(long userId, String username, MockHttpSession session) {}
}
