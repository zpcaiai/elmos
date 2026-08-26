package {{packageName}}.legacycompat;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

import java.util.Map;

/**
 * Preserves legacy form lifecycle: acquire scope -> reset -> populate -> convert -> validate.
 * Generator must create a per-form implementation from BindingConversionIR.
 */
public interface LegacyFormLifecycleBinder<T> {

    T acquire(HttpServletRequest request);

    void reset(T form, HttpServletRequest request);

    void populate(T form, Map<String, String[]> parameters, DataBinder binder);

    void validate(T form, BindingResult errors, HttpServletRequest request);

    default T bind(HttpServletRequest request, DataBinder binder) {
        T form = acquire(request);
        reset(form, request);
        populate(form, request.getParameterMap(), binder);
        validate(form, binder.getBindingResult(), request);
        return form;
    }
}
