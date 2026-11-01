package sa.minjaz.preview;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.View;
import android.widget.TextView;

/** Shared Android-native brand styling and resolution-independent line icons.
 * No emoji/glyph icon fonts, external image hosts or bundled third-party fonts.
 */
public final class MinjazStyle {
    public static final int PURPLE = Color.rgb(101, 88, 245);
    public static final int DEEP = Color.rgb(43, 30, 104);
    public static final int INK = Color.rgb(24, 25, 49);
    public static final int MUTED = Color.rgb(105, 111, 132);
    public static final int CANVAS = Color.rgb(248, 248, 252);
    public static final int PALE = Color.rgb(242, 239, 255);
    public static final int BORDER = Color.rgb(232, 231, 241);

    private MinjazStyle() {}

    public static GradientDrawable surface(Context context, int fill, int radiusDp, boolean stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(dp(context, radiusDp));
        if (stroke) drawable.setStroke(dp(context, 1), BORDER);
        return drawable;
    }

    public static int dp(Context context, int value) {
        return (int)(value * context.getResources().getDisplayMetrics().density + 0.5f);
    }

    public static void text(TextView label, boolean strong) {
        // Platform Arabic fallback (including proper RTL shaping and font scale).
        label.setTypeface(Typeface.create("sans-serif",
            strong ? Typeface.BOLD : Typeface.NORMAL));
        label.setIncludeFontPadding(true);
        label.setLineSpacing(dp(label.getContext(), 2), 1f);
    }

    public static View icon(Context context, int kind, int color) {
        return new Glyph(context, kind, color);
    }

    public static final int GRID = 0, BRIEFCASE = 1, INBOX = 2,
        SERVICES = 3, USER = 4, SEARCH = 5, CHEVRON = 6, MARK = 7;

    public static final class Glyph extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final int kind;
        private int tint;

        Glyph(Context context, int kind, int color) {
            super(context);
            this.kind = kind;
            tint = color;
            setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
        }

        public void setTint(int color) {
            tint = color;
            invalidate();
        }

        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            canvas.save();
            float size = Math.min(getWidth(), getHeight());
            canvas.translate((getWidth() - size)/2f, (getHeight() - size)/2f);
            canvas.scale(size/28f, size/28f);
            paint.setColor(tint);
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(2f);
            paint.setStrokeCap(Paint.Cap.ROUND);
            paint.setStrokeJoin(Paint.Join.ROUND);
            switch(kind) {
                case GRID:
                    for (int i=0; i<2; i++) for (int j=0; j<2; j++)
                        canvas.drawRoundRect(new RectF(4+j*11,4+i*11,12+j*11,12+i*11),
                            1.8f,1.8f,paint);
                    break;
                case BRIEFCASE:
                    canvas.drawRoundRect(new RectF(3,9,25,23),2.6f,2.6f,paint);
                    canvas.drawRoundRect(new RectF(10,5,18,9),1.5f,1.5f,paint);
                    canvas.drawLine(3,15,25,15,paint);
                    canvas.drawLine(12,13.5f,16,13.5f,paint);
                    break;
                case INBOX:
                    canvas.drawRoundRect(new RectF(4,7,24,23),2.6f,2.6f,paint);
                    canvas.drawLine(4,15,10,15,paint);
                    canvas.drawLine(10,15,12,18,paint);
                    canvas.drawLine(12,18,16,18,paint);
                    canvas.drawLine(16,18,18,15,paint);
                    canvas.drawLine(18,15,24,15,paint);
                    break;
                case SERVICES:
                    canvas.drawRoundRect(new RectF(4,9,24,24),2.6f,2.6f,paint);
                    canvas.drawLine(4,13,24,13,paint);
                    canvas.drawLine(10,9,10,6,paint);
                    canvas.drawLine(18,9,18,6,paint);
                    canvas.drawLine(10,6,18,6,paint);
                    canvas.drawLine(14,16,14,21,paint);
                    canvas.drawLine(11.5f,18.5f,16.5f,18.5f,paint);
                    break;
                case USER:
                    canvas.drawCircle(14,10,5,paint);
                    canvas.drawArc(new RectF(4,15,24,27),190,160,false,paint);
                    canvas.drawCircle(14,14,12,paint);
                    break;
                case SEARCH:
                    canvas.drawCircle(12,12,7,paint);
                    canvas.drawLine(17.2f,17.2f,24,24,paint);
                    break;
                case CHEVRON:
                    Path arrow = new Path();
                    arrow.moveTo(17,6); arrow.lineTo(10,14); arrow.lineTo(17,22);
                    canvas.drawPath(arrow,paint);
                    break;
                case MARK:
                    // Match public/icon.svg and the real launcher symbol.
                    paint.setStyle(Paint.Style.FILL);
                    paint.setColor(Color.rgb(44, 201, 183));
                    Path low = new Path();
                    low.moveTo(5,19); low.lineTo(15,19); low.lineTo(17,15);
                    low.lineTo(7,15); low.close();
                    canvas.drawPath(low, paint);
                    paint.setColor(Color.rgb(138, 125, 255));
                    Path mid = new Path();
                    mid.moveTo(7,14); mid.lineTo(18,14); mid.lineTo(20,10);
                    mid.lineTo(9,10); mid.close();
                    canvas.drawPath(mid, paint);
                    paint.setColor(PURPLE);
                    Path high = new Path();
                    high.moveTo(9,9); high.lineTo(21,9); high.lineTo(19,13);
                    high.lineTo(7,13); high.close();
                    canvas.drawPath(high, paint);
                    paint.setColor(DEEP);
                    paint.setStyle(Paint.Style.STROKE);
                    paint.setStrokeWidth(1.8f);
                    Path tick = new Path();
                    tick.moveTo(19,18); tick.lineTo(21,20); tick.lineTo(25,16);
                    canvas.drawPath(tick, paint);
                    break;
                default: break;
            }
            canvas.restore();
        }
    }
}
